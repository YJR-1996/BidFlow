<!-- ComplianceReportView.vue - Compliance report with risk analysis -->
<template>
  <div class="compliance-page">
    <!-- Header -->
    <div class="report-header">
      <div class="header-left">
        <div class="breadcrumb">
          <span>项目</span>
          <span>/</span>
          <span>{{ projectName }}</span>
          <span>/</span>
          <span class="text-primary">合规核查报告</span>
        </div>
        <h1>智能合规核查报告</h1>
        <p class="meta">最后更新：{{ lastUpdate }} · AI 深度扫描完成</p>
      </div>
      <div class="header-actions">
        <el-button @click="downloadMarkdown">
          <template #icon><span class="material-symbols-outlined">description</span></template>
          导出 Markdown
        </el-button>
        <el-button @click="downloadPDF">
          <template #icon><span class="material-symbols-outlined">picture_as_pdf</span></template>
          导出 PDF
        </el-button>
        <el-button type="primary" :loading="rechecking" @click="handleRecheck">
          <template #icon><span class="material-symbols-outlined" :class="{ 'animate-spin': rechecking }">refresh</span></template>
          {{ rechecking ? '核查中...' : '重新核查' }}
        </el-button>
      </div>
    </div>

    <!-- Stats cards + circular progress -->
    <div class="stats-grid">
      <div v-for="stat in stats" :key="stat.label" class="stat-card">
        <div class="stat-top">
          <span class="stat-icon-wrap" :class="stat.iconBg">
            <span class="material-symbols-outlined" :class="stat.iconColor">{{ stat.icon }}</span>
          </span>
          <el-tag v-if="rechecking" size="small">加载中</el-tag>
        </div>
        <div class="stat-bottom">
          <span class="stat-label">{{ stat.label }}</span>
          <span class="stat-value">{{ rechecking ? '--' : stat.value }}</span>
        </div>
      </div>

      <!-- Circular progress card -->
      <div class="stat-card progress-card">
        <div class="circular-progress" :style="`--value: ${complianceScore}; --progress-color: #1a73e8;`">
          <div class="progress-inner">
            <span class="progress-pct">{{ rechecking ? '--' : complianceScore }}%</span>
            <span class="progress-label">合规率</span>
          </div>
        </div>
        <div class="progress-info">
          <h3>综合健康度</h3>
          <p>基于 {{ stats[0]?.value || 0 }} 项核心招标文件要求的实时核查结果。</p>
          <div class="progress-status">
            <span class="dot bg-success-green"></span>
            <span class="text-success-green font-bold">状态：良好</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Risk groups -->
    <div class="risk-sections">
      <div v-for="group in riskGroups" :key="group.severity" class="risk-group">
        <div class="risk-group-header">
          <div class="risk-accent" :class="group.accent"></div>
          <h3>{{ group.label }} <span class="risk-count">{{ group.items.length }}</span></h3>
        </div>

        <div v-if="rechecking" class="risk-skeleton">
          <div v-for="i in 2" :key="i" class="skeleton-card">
            <div class="skeleton-avatar"></div>
            <div class="skeleton-content">
              <div class="skeleton-line w-1/4"></div>
              <div class="skeleton-line w-3/4"></div>
            </div>
          </div>
        </div>

        <div v-else class="risk-list">
          <div
            v-for="risk in group.items"
            :key="risk.id"
            :class="['risk-card', { expanded: expandedRisk === risk.id }]"
          >
            <div class="risk-card-header" @click="toggleRisk(risk.id)">
              <div class="risk-icon" :class="group.iconBg">
                <span class="material-symbols-outlined" :class="group.iconColor">{{ group.icon }}</span>
              </div>
              <div class="risk-info">
                <h4>{{ risk.title }}</h4>
                <p>关联条款：{{ risk.requirement }}</p>
              </div>
              <span class="material-symbols-outlined expand-icon" :class="{ 'rotate-180': expandedRisk === risk.id }">expand_more</span>
            </div>

            <div v-show="expandedRisk === risk.id" class="risk-card-body">
              <div class="risk-detail-grid">
                <div class="detail-col">
                  <div>
                    <span class="detail-label">问题详述</span>
                    <p class="detail-value">{{ risk.description }}</p>
                  </div>
                  <div class="risk-cause">
                    <span class="detail-label">成因分析</span>
                    <p class="detail-value">{{ risk.cause }}</p>
                  </div>
                </div>
                <div class="detail-col">
                  <div class="ai-suggestion">
                    <span class="detail-label">AI 修复建议</span>
                    <p class="detail-value">{{ risk.suggestion }}</p>
                    <el-button size="small" type="primary" class="suggestion-btn">
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { ElMessage } from 'element-plus'
import { runComplianceCheck as runComplianceCheckApi, getComplianceReport as getComplianceReportApi } from '@/api/compliance'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

const rechecking = ref(false)
const complianceScore = ref(86)
const expandedRisk = ref(null)
const complianceReportData = ref(null)

const projectName = computed(() => {
  const id = route.params.projectId
  const project = projectStore.projects.find(p => p.id === id)
  return project?.name || '加载中...'
})

const lastUpdate = ref(new Date().toLocaleString('zh-CN'))

const stats = computed(() => {
  if (!complianceReportData.value) {
    return [
      { label: '核查总项', value: '--', icon: 'list_alt', iconBg: 'bg-surface-container', iconColor: 'text-primary' },
      { label: '已通过项', value: '--', icon: 'check_circle', iconBg: 'bg-success-green/10', iconColor: 'text-success-green' },
      { label: '待人工审核', value: '--', icon: 'pending', iconBg: 'bg-warning-amber/10', iconColor: 'text-warning-amber' },
      { label: '核查风险', value: '--', icon: 'report_problem', iconBg: 'bg-error-red/10', iconColor: 'text-error-red' }
    ]
  }
  const r = complianceReportData.value
  const total = r.total_requirements || 0
  const completed = r.completed_count || 0
  const pending = r.pending_review_count || 0
  const risks = r.risk_count || 0
  return [
    { label: '核查总项', value: String(total), icon: 'list_alt', iconBg: 'bg-surface-container', iconColor: 'text-primary' },
    { label: '已通过项', value: String(completed), icon: 'check_circle', iconBg: 'bg-success-green/10', iconColor: 'text-success-green' },
    { label: '待人工审核', value: String(pending), icon: 'pending', iconBg: 'bg-warning-amber/10', iconColor: 'text-warning-amber' },
    { label: '核查风险', value: String(risks), icon: 'report_problem', iconBg: 'bg-error-red/10', iconColor: 'text-error-red' }
  ]
})

const riskGroups = computed(() => {
  if (!complianceReportData.value) {
    return []
  }
  const r = complianceReportData.value
  const formatIssue = (issue) => ({
    id: issue.id,
    title: issue.description || '未知问题',
    requirement: issue.rule_code || '--',
    description: issue.description || '未提供描述',
    cause: '规则引擎检测到不合规项',
    suggestion: issue.suggestion || '需要人工检查'
  })
  return [
    {
      severity: 'high',
      label: '高风险项',
      accent: 'bg-error',
      icon: 'dangerous',
      iconBg: 'bg-error/10',
      iconColor: 'text-error',
      items: (r.high_risks || []).map(formatIssue)
    },
    {
      severity: 'medium',
      label: '中风险项',
      accent: 'bg-warning-amber',
      icon: 'warning',
      iconBg: 'bg-warning-amber/10',
      iconColor: 'text-warning-amber',
      items: (r.medium_risks || []).map(formatIssue)
    },
    {
      severity: 'low',
      label: '低风险项',
      accent: 'bg-success-green',
      icon: 'info',
      iconBg: 'bg-success-green/10',
      iconColor: 'text-success-green',
      items: (r.low_risks || []).map(formatIssue)
    }
  ]
})

function toggleRisk(id) {
  expandedRisk.value = expandedRisk.value === id ? null : id
}

async function handleRecheck() {
  rechecking.value = true
  complianceScore.value = 0
  try {
    const id = route.params.projectId
    if (id) {
      await runComplianceCheckApi(id)
      const res = await getComplianceReportApi(id)
      complianceReportData.value = res.data || {}
      complianceScore.value = Math.round(res.data?.completion_rate || 92)
      lastUpdate.value = new Date().toLocaleString('zh-CN')
      ElMessage.success('重新核查完成')
    }
  } catch {
    ElMessage.error('重新核查失败')
  } finally {
    rechecking.value = false
  }
}

function downloadMarkdown() {
  ElMessage.info('Markdown 导出功能开发中')
}

function downloadPDF() {
  ElMessage.info('PDF 导出功能开发中')
}

onMounted(() => {
  if (projectName.value === '加载中...') {
    projectStore.fetchProjects()
  }
  // Load compliance report
  const id = route.params.projectId
  if (id) {
    getComplianceReportApi(id).then(res => {
      complianceReportData.value = res.data || {}
      complianceScore.value = Math.round(res.data?.completion_rate || 0)
    }).catch(() => {
      // No report yet, use default
    })
  }
})
</script>

<style scoped>
.compliance-page {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

/* Header */
.report-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 24px;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--outline);
  margin-bottom: 8px;
}

.report-header h1 {
  font-size: 32px;
  font-weight: 700;
  color: var(--on-surface);
  margin-bottom: 4px;
}

.meta {
  font-size: 14px;
  color: var(--on-surface-variant);
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* Stats grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
}

.stat-card {
  background: white;
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.progress-card {
  flex-direction: row;
  align-items: center;
  gap: 16px;
}

.stat-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.stat-bottom {
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

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.bg-success-green { background: #34a853; }

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

/* Skeleton */
.risk-skeleton {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.skeleton-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: white;
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  animation: pulse 1.5s ease-in-out infinite;
}

.skeleton-avatar {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  background: var(--surface-container);
  flex-shrink: 0;
}

.skeleton-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}

.skeleton-line {
  height: 12px;
  background: var(--surface-container);
  border-radius: 4px;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Risk cards */
.risk-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.risk-card {
  background: white;
  border: 1px solid var(--outline-variant);
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

.risk-info p {
  font-size: 14px;
  color: var(--on-surface-variant);
}

.expand-icon {
  font-size: 28px !important;
  color: var(--outline);
  transition: transform 0.3s;
}

/* Risk body */
.risk-card-body {
  border-top: 1px solid var(--surface-container);
  padding: 24px;
  background: var(--surface-bright) / 0.3;
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
  background: var(--error-container) / 0.2;
  border-radius: 8px;
  border: 1px solid var(--error) / 0.1;
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

/* Color utilities */
.text-primary { color: var(--primary); }
.text-success-green { color: #34a853; }
.text-warning-amber { color: #fbbc04; }
.text-error { color: var(--error); }
.bg-surface-container { background: var(--surface-container); }
.bg-error\/10 { background: var(--error) / 0.1; }
.bg-success-green\/10 { background: #34a853 / 0.1; }
.bg-warning-amber\/10 { background: #fbbc04 / 0.1; }
.bg-error\/10 { background: var(--error) / 0.1; }
.font-bold { font-weight: 700; }

/* Responsive */
@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .report-header {
    flex-direction: column;
    align-items: flex-start;
  }
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .risk-detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
