<!-- ComplianceReport.vue - Shared compliance report component -->
<template>
  <div class="compliance-report">
    <!-- Loading state -->
    <div v-if="loading" class="skeleton-container">
      <div class="skeleton-cards">
        <div v-for="i in 4" :key="i" class="skeleton-card"></div>
      </div>
      <div class="skeleton-chart"></div>
      <div class="skeleton-lines">
        <div v-for="i in 3" :key="i" class="skeleton-line"></div>
      </div>
    </div>

    <template v-else>
      <!-- Stats grid + circular progress -->
      <div class="stats-grid">
        <div v-for="stat in statsList" :key="stat.label" class="stat-card" :class="stat.type">
          <div class="stat-icon-wrap" :class="stat.iconBg">
            <span class="material-symbols-outlined" :class="stat.iconColor">{{ stat.icon }}</span>
          </div>
          <div class="stat-info">
            <span class="stat-label">{{ stat.label }}</span>
            <span class="stat-value">{{ displayValue(stat) }}</span>
          </div>
        </div>
      </div>

      <!-- 一致性自检警告（防御性：若 3 段数字之和超出总项，后端统计口径异常，提示重新核查） -->
      <el-alert
        v-if="consistencyWarning"
        type="warning"
        :title="consistencyWarning"
        show-icon
        :closable="false"
        class="consistency-alert"
      />

      <!-- 综合健康度卡片：内容多，独立占一整行避免被 5 等分挤压 -->
      <div class="health-card-wrapper">
        <div class="stat-card progress-card health-card">
          <div
            class="circular-progress"
            :style="`--value: ${complianceScore}; --progress-color: ${healthColor};`"
          >
            <div class="progress-inner">
              <span class="progress-pct">{{ complianceScore }}%</span>
              <span class="progress-label">综合健康度</span>
            </div>
          </div>
          <div class="progress-info">
            <h3>综合健康度</h3>
            <p>基础×50% + 质量×30% + 合规×20% 加权计算</p>
            <div class="health-breakdown" v-if="reportData">
              <div class="health-item">
                <span>基础（响应覆盖）</span>
                <strong>{{ reportData.base_rate ?? 0 }}%</strong>
              </div>
              <div class="health-item">
                <span>质量（有来源引用）</span>
                <strong>{{ reportData.quality_rate ?? 0 }}%</strong>
              </div>
              <div class="health-item">
                <span>合规（无高风险未处理）</span>
                <strong>{{ reportData.compliance_rate ?? 0 }}%</strong>
              </div>
            </div>
            <div class="progress-status">
              <span class="dot" :style="{ background: healthColor }"></span>
              <span :style="{ color: healthColor }" class="font-bold">状态：{{ healthLabel }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Risk groups -->
      <div class="risk-sections">
        <div v-for="group in riskGroupList" :key="group.severity" class="risk-group">
          <div class="risk-group-header">
            <div class="risk-accent" :class="group.accent"></div>
            <h3>{{ group.label }} <span class="risk-count">({{ group.items.length }})</span></h3>
          </div>

          <div v-if="!group.items.length" class="empty-group">
            <span class="material-symbols-outlined text-outline">check_circle</span>
            <p>暂无{{ group.label }}</p>
          </div>

          <div v-else class="risk-list">
            <div
              v-for="(risk, i) in group.items"
              :key="i"
              :class="['risk-card', { expanded: expandedRisk === `${group.severity}-${i}` }]"
            >
              <div class="risk-card-header" @click="toggleRisk(group.severity, i)">
                <div class="risk-icon" :class="group.iconBg">
                  <span class="material-symbols-outlined" :class="group.iconColor">{{ group.icon }}</span>
                </div>
                <div class="risk-info">
                  <div class="risk-title-row">
                    <h4>{{ risk.title }}</h4>
                    <span v-if="risk.ruleCode" class="rule-code-tag" :title="risk.ruleCode">{{ ruleCodeLabel(risk.ruleCode) }}</span>
                  </div>
                  <p>关联需求：{{ risk.requirement }}</p>
                </div>
                <span
                  class="material-symbols-outlined expand-icon"
                  :class="{ 'rotate-180': expandedRisk === `${group.severity}-${i}` }"
                >expand_more</span>
              </div>

              <div v-show="expandedRisk === `${group.severity}-${i}`" class="risk-card-body">
                <div class="risk-detail-grid">
                  <div class="detail-col">
                    <div>
                      <span class="detail-label">问题详述</span>
                      <p class="detail-value">{{ risk.description }}</p>
                    </div>
                    <div class="risk-cause">
                      <span class="detail-label">关联需求</span>
                      <p class="detail-value">{{ risk.requirement }}</p>
                    </div>
                  </div>
                  <div class="detail-col">
                    <div class="ai-suggestion">
                      <span class="detail-label">AI 修复建议</span>
                      <p class="detail-value">{{ risk.suggestion }}</p>
                      <el-button size="small" type="primary" class="suggestion-btn" @click="emit('apply-suggestion', risk)">
                        应用建议
                      </el-button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  report: { type: Object, default: null },
  loading: { type: Boolean, default: false }
})

const emit = defineEmits(['recheck', 'export', 'apply-suggestion'])

const expandedRisk = ref(null)

// 计算合规分数（三维加权 overall，与 readiness_service 一致）
const reportData = computed(() => props.report || null)
const complianceScore = computed(() => {
  if (!props.report) return 0
  // 优先用后端三维加权 overall；缺失时退回响应覆盖率
  const overall = props.report.completion_rate
  if (typeof overall === 'number' && !isNaN(overall)) {
    return Math.round(overall)
  }
  const total = props.report.total_requirements || 0
  const completed = props.report.completed_count || 0
  return total > 0 ? Math.round((completed / total) * 100) : 0
})

// 状态分级：≥95 良好 / 80-94 需关注 / <80 待改进
const healthColor = computed(() => {
  const s = complianceScore.value
  if (s >= 95) return '#34a853'
  if (s >= 80) return '#fbbc04'
  return '#d93025'
})
const healthLabel = computed(() => {
  const s = complianceScore.value
  if (s >= 95) return '良好'
  if (s >= 80) return '需关注'
  return '待改进'
})

// 统计列表
const statsList = computed(() => [
  { key: 'total_requirements', label: '核查总项', icon: 'list_alt', type: '', iconBg: 'bg-surface-container', iconColor: 'text-primary', emptyValue: '--' },
  { key: 'completed_count', label: '已通过项', icon: 'check_circle', type: 'success', iconBg: 'bg-success-green/10', iconColor: 'text-success-green', emptyValue: '--' },
  { key: 'pending_review_count', label: '待人工审核', icon: 'pending', type: 'warning', iconBg: 'bg-warning-amber/10', iconColor: 'text-warning-amber', emptyValue: '--' },
  { key: 'risk_count', label: '核查风险', icon: 'report_problem', type: 'danger', iconBg: 'bg-error-red/10', iconColor: 'text-error-red', emptyValue: '--' }
])

function displayValue(stat) {
  if (props.loading) return '--'
  const val = props.report?.[stat.key]
  return val !== undefined && val !== null ? String(val) : stat.emptyValue
}

// 一致性自检：3 段互斥数字之和应 ≤ 总项；超出说明后端统计口径异常
const consistencyWarning = computed(() => {
  const r = props.report
  if (!r) return ''
  const total = r.total_requirements ?? 0
  const sum = (r.completed_count ?? 0) + (r.pending_review_count ?? 0) + (r.risk_count ?? 0)
  if (sum > total) {
    return `统计口径异常：${r.completed_count} + ${r.pending_review_count} + ${r.risk_count} = ${sum} > ${total}，请重新核查。`
  }
  return ''
})

// rule_code → 中文短标签（视觉区分同一需求触发的不同维度问题）
// 必须在顶层作用域定义，否则模板里 {{ ruleCodeLabel(...) }} 引用不到
const RULE_CODE_LABELS = {
  'P0_RESPONSE_MISSING': '响应缺失',
  'P0_SOURCE_MISSING': '资料缺失',
  'RESPONSE_CONTENT_EMPTY': '内容为空',
  'RESPONSE_SOURCE_MISSING': '来源缺失',
  'MANUAL_MATERIAL_REQUIRED': '需人工补充',
  'SEMANTIC_': '语义风险'
}
function ruleCodeLabel(code) {
  if (!code) return ''
  if (RULE_CODE_LABELS[code]) return RULE_CODE_LABELS[code]
  // SEMANTIC_xxx 系列统一显示"语义风险"
  if (code.startsWith('SEMANTIC_')) return RULE_CODE_LABELS['SEMANTIC_']
  return code
}

function formatIssue(issue) {
  return {
    id: issue.id || issue.rule_code || Math.random().toString(36).slice(2),
    title: issue.title || issue.description?.substring(0, 30) || issue.rule_code || '合规问题',
    description: issue.description || issue.detail || '无详细描述',
    requirement: issue.requirement_content || issue.requirement || issue.requirement_id || issue.rule_code || '--',
    ruleCode: issue.rule_code || '',
    suggestion: issue.suggestion || '需要人工检查',
    // L3：后端 level 是中文"高/中/低"，修正 severity 映射（原只认英文 high/medium → 恒落 low）
    severity: issue.severity || (issue.level === '高' ? 'high' : issue.level === '中' ? 'medium' : 'low')
  }
}

// 风险分组列表
const riskGroupList = computed(() => {
  if (!props.report) return []

  const groups = [
    {
      severity: 'high',
      label: '高风险项',
      accent: 'bg-error',
      icon: 'dangerous',
      iconBg: 'bg-error/10',
      iconColor: 'text-error',
      items: (props.report.high_risks || []).map(formatIssue)
    },
    {
      severity: 'medium',
      label: '中风险项',
      accent: 'bg-warning-amber',
      icon: 'warning',
      iconBg: 'bg-warning-amber/10',
      iconColor: 'text-warning-amber',
      items: (props.report.medium_risks || []).map(formatIssue)
    },
    {
      severity: 'low',
      label: '低风险项',
      accent: 'bg-success-green',
      icon: 'info',
      iconBg: 'bg-success-green/10',
      iconColor: 'text-success-green',
      items: (props.report.low_risks || []).map(formatIssue)
    }
  ]

  // L3：移除恒真 filter（原 `g.items.length > 0 || true` 恒不过滤，是死代码）
  return groups
})

function toggleRisk(severity, index) {
  const key = `${severity}-${index}`
  expandedRisk.value = expandedRisk.value === key ? null : key
}
</script>

<style scoped>
.compliance-report {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Skeleton loading */
.skeleton-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
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

.skeleton-lines {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton-line {
  height: 16px;
  background: var(--surface-container);
  border-radius: 4px;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Stats grid */
/* Stats grid — 现在只有 4 个统计卡片（综合健康度单独占行） */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card {
  background: white;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;  /* 改：图标固定顶部，不要 space-between 推到下面 */
  gap: 16px;                    /* 图标和 stat-info 之间留点间距 */
  min-height: 96px;
}

.stat-card.success { border-left: 4px solid #34a853; }
.stat-card.warning { border-left: 4px solid #fbbc04; }
.stat-card.danger { border-left: 4px solid var(--error); }

.progress-card {
  flex-direction: row;
  align-items: center;
  gap: 24px;
  min-height: auto;
}

/* 综合健康度卡片：单独占整行，宽度足够 */
.health-card-wrapper {
  margin-top: 16px;
}
.health-card {
  /* 复用 .stat-card 基础样式，覆盖其 layout */
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 32px;
  padding: 24px;
}

.stat-icon-wrap {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon-wrap .material-symbols-outlined {
  font-size: 24px;
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 12px;
}

.stat-label {
  font-size: 12px;
  color: var(--on-surface-variant);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: var(--on-surface);
}

/* Circular progress */
.circular-progress {
  width: 128px;
  height: 128px;
  flex-shrink: 0;
  position: relative;
  background: conic-gradient(var(--progress-color) calc(var(--value) * 1%), #e6f6ff 0);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.circular-progress::before {
  content: '';
  position: absolute;
  width: 80%;
  height: 80%;
  background: white;
  border-radius: 50%;
  z-index: 0;
}

.progress-inner {
  position: relative;
  z-index: 1;
  text-align: center;
}

.progress-pct {
  display: block;
  font-size: 24px;
  font-weight: 700;
  color: var(--primary);
}

.progress-label {
  font-size: 10px;
  color: var(--outline);
  text-transform: uppercase;
  font-weight: 700;
  letter-spacing: 0.1em;
}

.progress-info {
  flex: 1;
}

.progress-info h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--on-surface);
  margin-bottom: 4px;
}

.progress-info p {
  font-size: 14px;
  color: var(--on-surface-variant);
  margin-bottom: 8px;
}

.progress-status {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 三维健康度分解 */
.health-breakdown {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 10px 0;
  padding: 10px 12px;
  background: var(--surface-container-low);
  border-radius: 8px;
}

.health-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--on-surface-variant);
}

.health-item strong {
  font-size: 13px;
  color: var(--on-surface);
  font-weight: 700;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

/* Risk sections */
.risk-sections {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.risk-group-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.risk-accent {
  width: 4px;
  height: 24px;
  border-radius: 2px;
}

.risk-group-header h3 {
  font-size: 20px;
  font-weight: 700;
  color: var(--on-surface);
}

.risk-count {
  font-size: 14px;
  color: var(--on-surface-variant);
  opacity: 0.6;
  font-weight: 400;
}

.empty-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
  background: var(--surface-container-low);
  border-radius: 12px;
  color: var(--on-surface-variant);
}

.empty-group .material-symbols-outlined {
  font-size: 32px;
}

/* Risk list */
.risk-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.risk-card {
  background: white;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.risk-card.expanded {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  border-color: rgba(26, 115, 232, 0.2);
}

.risk-card-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  cursor: pointer;
  transition: background 0.2s;
}

.risk-card-header:hover {
  background: var(--surface-bright);
}

.risk-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.risk-icon .material-symbols-outlined {
  font-size: 24px;
}

.risk-info {
  flex: 1;
}

.risk-info h4 {
  font-size: 16px;
  font-weight: 700;
  color: var(--on-surface);
  margin-bottom: 4px;
}

/* 风险维度标签（区分同一需求触发的不同规则） */
.risk-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.risk-title-row h4 {
  margin-bottom: 0;
}

.rule-code-tag {
  flex-shrink: 0;
  font-size: 11px;
  line-height: 1;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(26, 115, 232, 0.08);
  border: 1px solid rgba(26, 115, 232, 0.2);
  color: var(--primary);
  font-weight: 600;
  white-space: nowrap;
  cursor: help;
}

.risk-info p {
  font-size: 14px;
  color: var(--on-surface-variant);
}

.expand-icon {
  font-size: 28px !important;
  color: var(--outline);
  transition: transform 0.3s;
}

.rotate-180 {
  transform: rotate(180deg);
}

/* Risk body */
.risk-card-body {
  border-top: 1px solid var(--surface-container);
  padding: 24px;
  background: rgba(243, 250, 255, 0.3);
}

.risk-detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
  margin-top: 16px;
}

.detail-label {
  display: block;
  font-size: 12px;
  color: var(--outline);
  text-transform: uppercase;
  font-weight: 700;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}

.detail-value {
  font-size: 14px;
  color: var(--on-surface);
  line-height: 1.6;
}

.risk-cause {
  padding: 12px;
  background: rgba(255, 218, 214, 0.2);
  border-radius: 8px;
  border: 1px solid rgba(186, 26, 26, 0.1);
  margin-top: 16px;
}

.risk-cause .detail-value {
  color: var(--on-surface-variant);
}

.ai-suggestion {
  padding: 16px;
  background: rgba(26, 115, 232, 0.05);
  border: 1px solid rgba(26, 115, 232, 0.1);
  border-radius: 12px;
  position: relative;
}

.suggestion-btn {
  margin-top: 12px;
}

/* Utility classes */
.text-primary { color: var(--primary); }
.text-success-green { color: #34a853; }
.text-warning-amber { color: #fbbc04; }
.text-error { color: var(--error); }
.text-outline { color: var(--outline); }
.font-bold { font-weight: 700; }

.bg-surface-container { background: var(--surface-container); }
.bg-error\/10 { background: rgba(186, 26, 26, 0.1); }
.bg-success-green\/10 { background: rgba(52, 168, 83, 0.1); }
.bg-warning-amber\/10 { background: rgba(251, 188, 4, 0.1); }
.bg-error { background-color: var(--error); }
.bg-warning-amber { background-color: var(--warning-amber); }
.bg-success-green { background-color: var(--success-green); }

/* Responsive */
@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .skeleton-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .skeleton-cards {
    grid-template-columns: repeat(2, 1fr);
  }
  .risk-detail-grid {
    grid-template-columns: 1fr;
  }
  .progress-card {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>