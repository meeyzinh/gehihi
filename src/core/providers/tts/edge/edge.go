package edge

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"time"
	"xiaozhi-server-go/src/core/providers/tts"

	"github.com/wujunwei928/edge-tts-go/edge_tts"
)

// Provider Edge TTS提供者实现
type Provider struct {
	*tts.BaseProvider
}

// NewProvider 创建Edge TTS提供者
func NewProvider(config *tts.Config, deleteFile bool) (*Provider, error) {
	base := tts.NewBaseProvider(config, deleteFile)
	return &Provider{
		BaseProvider: base,
	}, nil
}

func (p *Provider) toGoogleTTS(text string, outputDir string) (string, error) {
	tempFile := filepath.Join(outputDir, fmt.Sprintf("tts_google_%d.mp3", time.Now().UnixNano()))
	runes := []rune(text)
	if len(runes) > 150 {
		text = string(runes[:150])
	}
	ttsURL := fmt.Sprintf("https://translate.google.com/translate_tts?ie=UTF-8&q=%s&tl=vi&client=tw-ob", url.QueryEscape(text))

	req, err := http.NewRequest("GET", ttsURL, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("google tts request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("google tts returned status %d", resp.StatusCode)
	}

	audioData, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	if err := os.WriteFile(tempFile, audioData, 0644); err != nil {
		return "", err
	}
	return tempFile, nil
}

// ToTTS 将文本转换为音频文件，并返回文件路径
// 使用的edge库是github.com/wujunwei928/edge-tts-go，默认使用24k采样率
func (p *Provider) ToTTS(text string) (string, error) {
	// 获取配置的声音，如果未配置则使用默认值
	edgeTTSStartTime := time.Now()
	voice := p.BaseProvider.Config().Voice
	if voice == "" {
		voice = "vi-VN-HoaiMyNeural" // 默认声音
	}

	// 创建临时文件路径用于保存 edgeTTS 生成的 MP3
	outputDir := p.BaseProvider.Config().OutputDir
	if outputDir == "" {
		outputDir = os.TempDir() // Use system temp dir if not configured
	}
	// Ensure output directory exists
	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return "", fmt.Errorf("创建输出目录失败 '%s': %v", outputDir, err)
	}
	// Use a unique filename
	tempFile := filepath.Join(outputDir, fmt.Sprintf("edge_tts_go_%d.mp3", time.Now().UnixNano()))

	// 配置 edge-tts-go 连接选项
	connOptions := []edge_tts.CommunicateOption{
		edge_tts.SetVoice(voice),
	}

	// 创建 Communicate 实例
	conn, err := edge_tts.NewCommunicate(text, connOptions...)
	if err != nil {
		return p.toGoogleTTS(text, outputDir)
	}

	// 获取音频流数据
	audioData, err := conn.Stream()
	if err != nil {
		// Datacenter IP bị chặn websocket -> tự động chuyển sang Google TTS tiếng Việt miễn phí
		return p.toGoogleTTS(text, outputDir)
	}

	ttsDuration := time.Since(edgeTTSStartTime)
	_ = ttsDuration

	// 将音频数据写入临时文件
	err = os.WriteFile(tempFile, audioData, 0644)
	if err != nil {
		return p.toGoogleTTS(text, outputDir)
	}

	// 检查文件是否成功创建
	if _, err := os.Stat(tempFile); os.IsNotExist(err) {
		return p.toGoogleTTS(text, outputDir)
	}

	return tempFile, nil
}

func init() {
	// 注册Edge TTS提供者
	tts.Register("edge", func(config *tts.Config, deleteFile bool) (tts.Provider, error) {
		return NewProvider(config, deleteFile)
	})
	tts.Register("google", func(config *tts.Config, deleteFile bool) (tts.Provider, error) {
		return NewProvider(config, deleteFile)
	})
}
