<!-- RiskSummary.vue - Risk summary with report stats and recheck -->
<template>
  <div class="risk-summary">
    <!-- Loading state -->
    <div v-if="loading" class="skeleton-container">
      <div class="skeleton-header"></div>
      <div class="skeleton-cards">
        <div v-for="i in 4" :key="i" class="skeleton-card"></div>
      </div>
      <div class="skeleton-chart"></div>
    </div>

    <template v-else>
      <!-- Header actions -->
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

      <!-- Risk stats cards -->
      <div class="risk-stats">
        <div v-for="stat in riskStats" :key="stat.label" class="risk-stat-card" :class="stat.type">
          <div class="stat-icon">
            <span class="material-symbols-outlined">{{ stat.icon }}</span>
          </div>
          <div class="stat-info">
            <span class="stat-label">{{ stat.label }}</span>
            <span class="stat-value">{{ report[stat.key] || '--' }}</span>
          </div>
        </div>
      </div>

      <!-- Risk breakdown -->
      <div class="risk-breakdown">
        <h3>风险分布</h3>
        <div class="chart-placeholder">
          <div class="chart-bar-wrapper">
            <div v-for="(bar, i) in riskBars" :key="bar.label" class="chart-bar-item">
              <div class="bar-track">
                <div class="bar-fill" :style="`--width: ${(bar.value / report.totalItems) * 100}%; background: ${bar.color};`"></div>
              </div>
              <span class="bar-label">{{ bar.label }}</span>
              <span class="bar-value">{{ bar.value }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Risk items list -->
      <div class="risk-items">
        <h3>风险清单</h3>
        <div class="risk-item-list">
          <div v-for="(risk, i) in sampleRisks" :key="i" class="risk-item-card">
            <div class="risk-item-header">
              <span class="risk-severity" :class="risk.severity">{{ risk.severityLabel }}</span>
              <h4>{{ risk.title }}</h4>
            </div>
            <p>{{ risk.description }}</p>
            <div class="risk-item-meta">
              <span class="meta-item"><span class="material-symbols-outlined">link</span> {{ risk.requirement }}</span>
              <el-button size="small" type="primary" link @click="applyFix">应用修复建议</el-button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  report: { type: Object, default: null },
  loading: { type: Boolean, default: false }
})

const emit = defineEmits(['recheck'])

const sampleRisks = ref([
  {
    severity: 'high',
    severityLabel: '高风险',
    title: '资信证明文件缺失',
    description: '当前投标文件中未包含 2023 年度的企业信用等级证明（AAA级）。',
    requirement: '招标文件第 3.2.1 条 - 企业信用证明'
  },
  {
    severity: 'medium',
    severityLabel: '中风险',
    title: '商务条款偏差 - 质保期不足',
    description: '招标文件要求免费质保期不少于 36 个月，当前方案仅标注了 24 个月。',
    requirement: '招标文件第 5.1 条 - 售后服务要求'
  },
  {
    severity: 'low',
    severityLabel: '低风险',
    title: '格式建议 - 页码不连续',
    description: '投标书部分章节未添加页码，不符合标准格式要求。',
    requirement: '招标文件附录 A - 格式要求'
  }
])

const riskStats = computed(() => [
  { key: 'totalItems', label: '总项数', icon: 'list_alt', type: '' },
  { key: 'passedItems', label: '通过', icon: 'check_circle', type: 'success' },
  { key: 'pendingItems', label: '待审核', icon: 'pending', type: 'warning' },
  { key: 'riskItems', label: '风险', icon: 'warning', type: 'danger' }
])

const riskBars = computed(() => [
  { label: '已通过', value: props.report?.passedItems || 0, color: '#34a853' },
  { label: '待审核', value: props.report?.pendingItems || 0, color: '#fbbc04' },
  { label: '有风险', value: props.report?.riskItems || 0, color: '#ba1a1a' }
])

function exportReport() {
  ElMessage.success('报告导出中...')
}

function applyFix() {
  ElMessage.success('修复建议已应用')
}
</script>

<style scoped>
.risk-summary {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Skeleton */
.skeleton-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.skeleton-header {
  height: 48px;
  background: var(--surface-container);
  border-radius: 8px;
  animation: pulse 1.5s ease-in-out infinite;
}

.skeleton-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.skeleton-card {
  height: 96px;
  background: var(--surface-container);
  border-radius: 12px;
  animation: pulse 1.5s ease-in-out infinite;
}

.skeleton-chart {
  height: 200px;
  background: var(--surface-container);
  border-radius: 12px;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Header */
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

/* Risk stats */
.risk-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.risk-stat-card {
  background: white;
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  border-left: 4px solid var(--primary);
}

.risk-stat-card.success { border-left-color: #34a853; }
.risk-stat-card.warning { border-left-color: #fbbc04; }
.risk-stat-card.danger { border-left-color: var(--error); }

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  background: var(--primary-container) / 0.2;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-icon .material-symbols-outlined {
  font-size: 24px;
  color: var(--primary);
}

.risk-stat-card.success .stat-icon { background: #34a853 / 0.1; }
.risk-stat-card.warning .stat-icon { background: #fbbc04 / 0.1; }
.risk-stat-card.danger .stat-icon { background: var(--error) / 0.1; }

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-label {
  font-size: 12px;
  color: var(--on-surface-variant);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--on-surface);
}

/* Breakdown */
.risk-breakdown h3,
.risk-items h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--on-surface);
  margin-bottom: 16px;
}

.chart-placeholder {
  background: white;
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  padding: 24px;
}

.chart-bar-wrapper {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chart-bar-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bar-track {
  flex: 1;
  height: 24px;
  background: var(--surface-container);
  border-radius: 12px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 12px;
  width: 0;
  transition: width 0.6s ease;
}

.bar-label {
  font-size: 14px;
  color: var(--on-surface-variant);
  min-width: 60px;
}

.bar-value {
  font-size: 14px;
  font-weight: 700;
  color: var(--on-surface);
  min-width: 24px;
  text-align: right;
}

/* Risk items */
.risk-item-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.risk-item-card {
  background: white;
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  padding: 16px 20px;
}

.risk-item-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.risk-item-header h4 {
  font-size: 15px;
  font-weight: 600;
  color: var(--on-surface);
}

.risk-severity {
  font-size: 12px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 9999px;
  text-transform: uppercase;
}

.risk-severity.high { background: var(--error) / 0.1; color: var(--error); }
.risk-severity.medium { background: #fbbc04 / 0.1; color: #fbbc04; }
.risk-severity.low { background: #34a853 / 0.1; color: #34a853; }

.risk-item-card p {
  font-size: 14px;
  color: var(--on-surface-variant);
  line-height: 1.6;
  margin-bottom: 8px;
}

.risk-item-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--outline);
}

.meta-item .material-symbols-outlined {
  font-size: 16px;
}

/* Responsive */
@media (max-width: 768px) {
  .risk-stats {
    grid-template-columns: repeat(2, 1fr);
  }
  .skeleton-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
