package groq

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"xiaozhi-server-go/src/core/providers/asr"
	"xiaozhi-server-go/src/core/utils"
)

// Ensure Provider implements asr.Provider interface
var _ asr.Provider = (*Provider)(nil)

type Provider struct {
	*asr.BaseProvider
	apiKey     string
	apiURL     string
	model      string
	language   string
	sampleRate int
	logger     *utils.Logger
	mu         sync.Mutex
	audioBuf   bytes.Buffer
}

func NewProvider(config *asr.Config, deleteFile bool, logger *utils.Logger) (*Provider, error) {
	base := asr.NewBaseProvider(config, deleteFile)

	apiKey := ""
	if config.Data != nil {
		if k, ok := config.Data["api_key"].(string); ok {
			apiKey = k
		}
	}
	if apiKey == "" {
		if envKey := os.Getenv("GROQ_API_KEY"); envKey != "" {
			apiKey = envKey
		} else if envKey := os.Getenv("ASR_API_KEY"); envKey != "" {
			apiKey = envKey
		}
	}
	if apiKey == "" {
		return nil, fmt.Errorf("missing Groq API key")
	}

	apiURL := "https://api.groq.com/openai/v1/audio/transcriptions"
	if config.Data != nil {
		if u, ok := config.Data["url"].(string); ok && u != "" {
			apiURL = u
		}
	}

	model := "whisper-large-v3-turbo"
	if config.Data != nil {
		if m, ok := config.Data["model"].(string); ok && m != "" {
			model = m
		}
	}

	language := "vi"
	if config.Data != nil {
		if l, ok := config.Data["lang"].(string); ok && l != "" {
			language = l
		} else if l, ok := config.Data["language"].(string); ok && l != "" {
			language = l
		}
	}

	sampleRate := 16000
	if config.Data != nil {
		if sr, ok := config.Data["sample_rate"].(float64); ok && sr > 0 {
			sampleRate = int(sr)
		} else if sr, ok := config.Data["sample_rate"].(int); ok && sr > 0 {
			sampleRate = sr
		}
	}

	p := &Provider{
		BaseProvider: base,
		apiKey:       apiKey,
		apiURL:       apiURL,
		model:        model,
		language:     language,
		sampleRate:   sampleRate,
		logger:       logger,
	}
	p.InitAudioProcessing()
	return p, nil
}

func (p *Provider) SetUserPreferences(preferences map[string]interface{}) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	if sr, ok := preferences["sample_rate"].(int); ok && sr > 0 {
		p.sampleRate = sr
	}
	if lang, ok := preferences["language"].(string); ok && lang != "" {
		p.language = lang
	}
	return nil
}

func (p *Provider) Reset() error {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.audioBuf.Reset()
	return nil
}

func (p *Provider) CloseConnection() error {
	return p.Reset()
}

func (p *Provider) AddAudio(data []byte) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	if len(data) > 0 {
		p.audioBuf.Write(data)
	}
	return nil
}

func createWavData(pcm []byte, sampleRate int, numChannels int) []byte {
	totalDataLen := uint32(len(pcm))
	totalAudioLen := totalDataLen + 36
	byteRate := uint32(sampleRate * numChannels * 2)

	var header [44]byte
	copy(header[0:4], []byte("RIFF"))
	binary.LittleEndian.PutUint32(header[4:8], totalAudioLen)
	copy(header[8:12], []byte("WAVE"))
	copy(header[12:16], []byte("fmt "))
	binary.LittleEndian.PutUint32(header[16:20], 16) // Subchunk1Size
	binary.LittleEndian.PutUint16(header[20:22], 1)  // AudioFormat (PCM)
	binary.LittleEndian.PutUint16(header[22:24], uint16(numChannels))
	binary.LittleEndian.PutUint32(header[24:28], uint32(sampleRate))
	binary.LittleEndian.PutUint32(header[28:32], byteRate)
	binary.LittleEndian.PutUint16(header[32:34], uint16(numChannels*2)) // BlockAlign
	binary.LittleEndian.PutUint16(header[34:36], 16)                    // BitsPerSample
	copy(header[36:40], []byte("data"))
	binary.LittleEndian.PutUint32(header[40:44], totalDataLen)

	buf := make([]byte, 44+len(pcm))
	copy(buf[0:44], header[:])
	copy(buf[44:], pcm)
	return buf
}

func (p *Provider) SendLastAudio(data []byte) error {
	p.mu.Lock()
	if len(data) > 0 {
		p.audioBuf.Write(data)
	}
	pcmBytes := make([]byte, p.audioBuf.Len())
	copy(pcmBytes, p.audioBuf.Bytes())
	p.audioBuf.Reset()
	sampleRate := p.sampleRate
	p.mu.Unlock()

	// If audio is shorter than ~0.15s, skip
	if len(pcmBytes) < 3200 {
		return nil
	}

	go func(pcm []byte, rate int) {
		wavData := createWavData(pcm, rate, 1)

		var reqBody bytes.Buffer
		writer := multipart.NewWriter(&reqBody)
		part, err := writer.CreateFormFile("file", "audio.wav")
		if err != nil {
			if p.logger != nil {
				p.logger.Error(fmt.Sprintf("Tạo form file thất bại: %v", err))
			}
			return
		}
		if _, err := part.Write(wavData); err != nil {
			if p.logger != nil {
				p.logger.Error(fmt.Sprintf("Ghi dữ liệu WAV thất bại: %v", err))
			}
			return
		}
		_ = writer.WriteField("model", p.model)
		if p.language != "" {
			_ = writer.WriteField("language", p.language)
		}
		writer.Close()

		req, err := http.NewRequest("POST", p.apiURL, &reqBody)
		if err != nil {
			if p.logger != nil {
				p.logger.Error(fmt.Sprintf("Tạo HTTP request ASR thất bại: %v", err))
			}
			return
		}
		req.Header.Set("Content-Type", writer.FormDataContentType())
		req.Header.Set("Authorization", "Bearer "+p.apiKey)

		client := &http.Client{Timeout: 15 * time.Second}
		resp, err := client.Do(req)
		if err != nil {
			if p.logger != nil {
				p.logger.Error(fmt.Sprintf("Gọi Groq Whisper API thất bại: %v", err))
			}
			return
		}
		defer resp.Body.Close()

		respBytes, err := io.ReadAll(resp.Body)
		if err != nil {
			if p.logger != nil {
				p.logger.Error(fmt.Sprintf("Đọc phản hồi Groq ASR thất bại: %v", err))
			}
			return
		}

		if resp.StatusCode != http.StatusOK {
			if p.logger != nil {
				p.logger.Error(fmt.Sprintf("Groq Whisper API trả về mã lỗi %d: %s", resp.StatusCode, string(respBytes)))
			}
			return
		}

		var res struct {
			Text string `json:"text"`
		}
		if err := json.Unmarshal(respBytes, &res); err != nil {
			if p.logger != nil {
				p.logger.Error(fmt.Sprintf("Giải mã JSON phản hồi Groq thất bại: %v", err))
			}
			return
		}

		text := strings.TrimSpace(res.Text)
		if p.logger != nil {
			p.logger.Info(fmt.Sprintf("[Groq Whisper ASR] Nhận diện thành công: %s", text))
		}

		if text != "" {
			if listener := p.GetListener(); listener != nil {
				listener.OnAsrResult(text, true)
			}
		}
	}(pcmBytes, sampleRate)

	return nil
}

func (p *Provider) Transcribe(ctx context.Context, audioData []byte) (string, error) {
	wavData := createWavData(audioData, p.sampleRate, 1)

	var reqBody bytes.Buffer
	writer := multipart.NewWriter(&reqBody)
	part, err := writer.CreateFormFile("file", "audio.wav")
	if err != nil {
		return "", err
	}
	if _, err := part.Write(wavData); err != nil {
		return "", err
	}
	_ = writer.WriteField("model", p.model)
	if p.language != "" {
		_ = writer.WriteField("language", p.language)
	}
	writer.Close()

	req, err := http.NewRequestWithContext(ctx, "POST", p.apiURL, &reqBody)
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())
	req.Header.Set("Authorization", "Bearer "+p.apiKey)

	client := &http.Client{Timeout: 15 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("groq asr status %d: %s", resp.StatusCode, string(respBytes))
	}

	var res struct {
		Text string `json:"text"`
	}
	if err := json.Unmarshal(respBytes, &res); err != nil {
		return "", err
	}
	return strings.TrimSpace(res.Text), nil
}

func init() {
	asr.Register("groq", func(config *asr.Config, deleteFile bool, logger *utils.Logger) (asr.Provider, error) {
		return NewProvider(config, deleteFile, logger)
	})
	asr.Register("whisper", func(config *asr.Config, deleteFile bool, logger *utils.Logger) (asr.Provider, error) {
		return NewProvider(config, deleteFile, logger)
	})
	asr.Register("openai", func(config *asr.Config, deleteFile bool, logger *utils.Logger) (asr.Provider, error) {
		return NewProvider(config, deleteFile, logger)
	})
}
