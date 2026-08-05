<!-- RiskSummary.vue - Thin wrapper using shared ComplianceReport component -->
<template>
  <div class="risk-summary">
    <!-- Header actions only -->
    <div class="risk-header">
      <div>
        <h2>风险摘要</h2>
        <p class="risk-meta">基于项目合规核查结果的自动风险分析</p>
      </div>
      <div class="risk-actions">
        <el-button @click="emit('recheck')">
          <template #icon><span class="material-symbols-outlined">refresh</span></template>
          重新核查
        </el-button>
        <el-button type="primary" @click="exportReport">导出报告</el-button>
      </div>
    </div>

    <!-- Shared compliance report component -->
    <ComplianceReport
      :report="report"
      :loading="loading"
      @apply-suggestion="applyFix"
    />
  </div>
</template>

<script setup>
import ComplianceReport from './ComplianceReport.vue'

const props = defineProps({
  report: { type: Object, default: null },
  loading: { type: Boolean, default: false }
})

const emit = defineEmits(['recheck', 'export', 'apply-fix'])

function exportReport() {
  emit('export')
}

function applyFix(item) {
  if (item?.suggestion) {
    emit('apply-fix', item)
  }
}
</script>

<style scoped>
.risk-summary {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.risk-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.risk-header h2 {
  font-size: 24px;
  font-weight: 700;
  color: var(--on-surface);
  margin-bottom: 4px;
}

.risk-meta {
  font-size: 14px;
  color: var(--on-surface-variant);
}

.risk-actions {
  display: flex;
  gap: 8px;
}
</style>