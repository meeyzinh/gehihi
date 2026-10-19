<template>
  <div class="copyright">
    <div class="footer-content">
      <span>© {{ year || 2026 }} {{ name || 'Gehihi Server' }} {{ version ? 'v' + version : '' }}</span>
    </div>
  </div>
</template>

<script>
import { mapState } from 'vuex';

export default {
  name: 'VersionFooter',
  computed: {
    ...mapState({
      version: state => state.pubConfig.version,
      name: state => state.pubConfig.name,
      year: state => state.pubConfig.year
    })
  },
  mounted() {
    this.$store.dispatch('fetchPubConfig')
  }
}
</script>

<style scoped>
.copyright {
  padding: 10px 0;
}

.footer-content {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  color: #888;
  font-size: 13px;
}
</style>