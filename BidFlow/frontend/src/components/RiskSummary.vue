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
        <!-- P1：项目级补救按钮（原每条风险卡片的"应用建议"提升至此，避免重复/误导） -->
        <el-tooltip content="生成项目级补救计划：缺失的响应自动重新生成、缺资料的引导上传企业资料、其余标记人工处理。作用于本项目的全部未处理风险。">
          <el-button type="primary" plain @click="emit('apply-fix')">
            <template #icon><span class="material-symbols-outlined">tips_and_updates</span></template>
            生成补救计划
          </el-button>
        </el-tooltip>
        <el-button type="primary" @click="exportReport">导出报告</el-button>
      </div>
    </div>

    <!-- Shared compliance report component -->
    <ComplianceReport
      :report="report"
      :loading="loading"
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