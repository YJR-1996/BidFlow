<!-- AnalyticsView.vue - Statistics dashboard with real backend data -->
<template>
  <div class="analytics-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <h1 class="page-title">统计报表</h1>
        <p class="page-desc">
          项目执行数据实时统计与趋势分析
          <span v-if="lastUpdated" class="update-time">· 更新于 {{ lastUpdated }}</span>
        </p>
      </div>
      <div class="header-actions">
        <!-- M37：项目选择器（联动刷新），默认"全部项目" -->
        <el-select
          v-model="selectedProjectId"
          placeholder="选择项目"
          class="period-select"
          clearable
          style="width: 200px"
        >
          <el-option label="全部项目" :value="null" />
          <el-option
            v-for="p in projects"
            :key="p.id"
            :label="p.name"
            :value="p.id"
          />
        </el-select>
        <el-select v-model="selectedPeriod" placeholder="时间范围" class="period-select" @change="loadStats">
          <el-option label="近7天" value="7d" />
          <el-option label="近30天" value="30d" />
          <el-option label="近90天" value="90d" />
        </el-select>
        <el-button @click="loadStats" :loading="loading">
          <template #icon><span class="material-symbols-outlined">refresh</span></template>
          刷新
        </el-button>
      </div>
    </div>

    <!-- M37：当前视图标识条（项目 + 时间维度） -->
    <div v-if="stats" class="scope-banner">
      <span class="material-symbols-outlined">dataset</span>
      <span>当前视图：<strong>{{ scopeName }}</strong> · {{ periodName }}</span>
    </div>

    <!-- Loading Skeleton -->
    <div v-if="loading" class="skeleton-container">
      <div class="skeleton-cards">
        <div v-for="i in 4" :key="i" class="skeleton-card"></div>
      </div>
      <div class="skeleton-row">
        <div class="skeleton-chart"></div>
        <div class="skeleton-chart"></div>
      </div>
      <div class="skeleton-chart large"></div>
    </div>

    <template v-else-if="stats">
      <!-- 核心指标卡片 -->
      <div class="metrics-row">
        <div v-for="metric in coreMetrics" :key="metric.label" class="metric-card">
          <div class="metric-header">
            <span class="metric-label">{{ metric.label }}</span>
            <span
              class="metric-icon material-symbols-outlined"
              :class="metric.iconColor"
            >{{ metric.icon }}</span>
          </div>
          <div class="metric-body">
            <span class="metric-value">{{ metric.value }}</span>
            <span
              class="metric-trend"
              :class="metric.trend > 0 ? 'up' : metric.trend < 0 ? 'down' : 'flat'"
            >
              <span class="material-symbols-outlined">
                {{ metric.trend > 0 ? 'trending_up' : metric.trend < 0 ? 'trending_down' : 'trending_flat' }}
              </span>
              {{ Math.abs(metric.trend) }}%
            </span>
          </div>
          <div class="metric-footer">
            <span class="metric-compare">较上周期</span>
          </div>
        </div>
      </div>

      <!-- 图表区域 -->
      <div class="charts-grid">
        <!-- 项目状态分布 -->
        <div class="chart-card">
          <div class="chart-header">
            <h3>项目状态分布</h3>
            <span class="chart-subtitle">当前活跃项目</span>
          </div>
          <div class="chart-body">
            <div class="status-chart">
              <div v-for="item in statusDistribution" :key="item.label" class="status-bar-item">
                <div class="status-bar-label">
                  <span class="status-dot" :style="{ background: item.color }"></span>
                  <span>{{ item.label }}</span>
                </div>
                <div class="status-bar-track">
                  <div
                    class="status-bar-fill"
                    :style="{ width: item.percentage + '%', background: item.color }"
                  ></div>
                </div>
                <span class="status-value">{{ item.count }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 效率指标 -->
        <div class="chart-card">
          <div class="chart-header">
            <h3>效率指标</h3>
            <span class="chart-subtitle">基于真实项目数据计算</span>
          </div>
          <div class="chart-body">
            <div class="efficiency-list">
              <div v-for="item in efficiencyMetrics" :key="item.label" class="efficiency-item">
                <div class="efficiency-icon" :style="{ background: item.bgColor }">
                  <span class="material-symbols-outlined" :style="{ color: item.color }">
                    {{ item.icon }}
                  </span>
                </div>
                <div class="efficiency-info">
                  <span class="efficiency-label">{{ item.label }}</span>
                  <span class="efficiency-value">{{ item.value }}</span>
                </div>
                <span class="efficiency-unit">{{ item.unit }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 趋势区域（M37：风险新增时间序列，按项目+时间窗口） -->
      <div class="trend-card">
        <div class="chart-header">
          <h3>风险新增趋势</h3>
          <div class="legend-row">
            <span class="legend-item">
              <span class="legend-dot" style="background: #ba1a1a"></span>新增风险
            </span>
          </div>
        </div>
        <div class="chart-body">
          <div class="trend-chart">
            <div class="chart-grid">
              <div v-for="(point, i) in [1, 2, 3, 4]" :key="i" class="grid-line" :style="{ bottom: ((i - 1) * 25) + '%' }"></div>
            </div>
            <div class="chart-bars">
              <div v-for="(day, i) in trendChart" :key="i" class="bar-group">
                <div class="bar-pair">
                  <div class="bar bar-risk" :style="{ height: (day.new_risks || 0) / maxTrendValue * 100 + '%' }"></div>
                </div>
                <span class="bar-label">{{ day.label }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 风险与合规概览 -->
      <div class="overview-grid">
        <div class="overview-card risk-overview">
          <div class="overview-header">
            <h3>风险概览</h3>
            <span class="overview-badge risk-badge-pill" :class="{ 'has-risk': totalRisks > 0 }">
              <span class="material-symbols-outlined risk-badge-icon">shield</span>
              {{ totalRisks }} 项待处理
            </span>
          </div>
          <div class="overview-body">
            <!-- 等级卡：大数字 + 图标 + 标签（扫读层） -->
            <div class="risk-card-grid">
              <div
                v-for="level in riskLevels"
                :key="level.label"
                class="risk-card"
                :class="'risk-card-' + level.key"
              >
                <span class="material-symbols-outlined risk-card-icon">{{ riskIcon(level.key) }}</span>
                <span class="risk-card-num">{{ level.count }}</span>
                <span class="risk-card-label">{{ level.label }}</span>
              </div>
            </div>
            <!-- 构成条：按比例分段着色（比例层） -->
            <div class="risk-compose" v-if="riskLevels.length">
              <div class="risk-compose-bar" role="img" :aria-label="riskComposeAria">
                <div
                  v-for="level in riskLevels"
                  :key="'bar-' + level.label"
                  class="risk-compose-seg"
                  :style="{ width: level.percentage + '%', background: level.color }"
                ></div>
              </div>
              <div class="risk-compose-legend">
                <span v-for="level in riskLevels" :key="'lg-' + level.label" class="risk-compose-item">
                  <span class="risk-compose-dot" :style="{ background: level.color }"></span>
                  {{ level.label }} {{ level.count }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div class="overview-card compliance-overview">
          <div class="overview-header">
            <h3>合规健康度</h3>
            <span class="compliance-score">{{ complianceScore }}%</span>
          </div>
          <div class="overview-body">
            <div class="compliance-ring">
              <svg viewBox="0 0 36 36" class="ring-chart">
                <path
                  class="ring-bg"
                  d="M18 2.5 a15.5 15.5 0 0 1 0 31 a15.5 15.5 0 0 1 0 -31"
                />
                <path
                  class="ring-progress"
                  :stroke-dasharray="`${complianceScore}, 100`"
                  d="M18 2.5 a15.5 15.5 0 0 1 0 31 a15.5 15.5 0 0 1 0 -31"
                />
              </svg>
              <div class="ring-label">
                <span class="ring-value">{{ complianceScore }}%</span>
                <span class="ring-text">综合健康度</span>
              </div>
            </div>
            <div class="compliance-stats">
              <div class="compliance-stat">
                <span class="stat-num">{{ totalItems }}</span>
                <span class="stat-label">核查总项</span>
              </div>
              <div class="compliance-stat">
                <span class="stat-num">{{ passedItems }}</span>
                <span class="stat-label">已通过</span>
              </div>
              <div class="compliance-stat">
                <span class="stat-num">{{ pendingItems }}</span>
                <span class="stat-label">待审核</span>
              </div>
            </div>
            <!-- M37：未达标项清单（方案A：仅含未处理合规风险的需求，显示所属项目，可点击跳转） -->
            <div class="compliance-pending" v-if="pendingRequirements.length">
              <div class="pending-title">未达标项（前 {{ pendingRequirements.length }}）</div>
              <div
                v-for="req in pendingRequirements"
                :key="req.requirement_id"
                class="pending-item"
                @click="goToProject(req)"
                title="点击跳转到该项目查看详情"
              >
                <span class="material-symbols-outlined pending-icon">error_outline</span>
                <span class="pending-text">{{ req.content }}</span>
                <el-tag size="small" :type="req.priority === 'P0' ? 'danger' : req.priority === 'P1' ? 'warning' : 'info'">
                  {{ req.priority }}
                </el-tag>
                <el-tag size="small" type="info" class="pending-project">{{ req.project_name }}</el-tag>
                <span class="pending-link">查看项目 →</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Empty state -->
    <div v-else class="empty-state">
      <span class="material-symbols-outlined">analytics</span>
      <h2>暂无统计数据</h2>
      <p>创建项目并上传招标文件后，系统将自动生成统计报表</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getStats } from '@/api/stats'
import { getProjects } from '@/api/projects'
import { parseResponse } from '@/utils/api'
import { parseServerDate } from '@/utils/date'
import { ElMessage } from 'element-plus'

const router = useRouter()

// 未达标项 → 一键跳转到对应项目详情页（合规风险所在项目）
function goToProject(req) {
  if (!req?.project_id) return
  router.push({ path: `/project/${req.project_id}` })
}

const selectedPeriod = ref('30d')
const selectedProjectId = ref(null)  // null = 全部项目
const projects = ref([])
const loading = ref(false)
const stats = ref(null)
const lastUpdated = ref('')

// 联动刷新：项目或时间维度变化时重新加载
watch([selectedProjectId, selectedPeriod], () => loadStats())

async function loadProjects() {
  try {
    const res = await getProjects()
    projects.value = parseResponse(res, []) || []
  } catch (e) {
    console.warn('[AnalyticsView] 加载项目列表失败：', e)
  }
}

async function loadStats() {
  loading.value = true
  try {
    const res = await getStats(selectedPeriod.value, selectedProjectId.value)
    const data = parseResponse(res, null)
    stats.value = data
    if (data?.updated_at) {
      const d = parseServerDate(data.updated_at)
      if (d) lastUpdated.value = d.toLocaleString('zh-CN')
    }
  } catch (error) {
    ElMessage.error(error.message || '加载统计数据失败')
  } finally {
    loading.value = false
  }
}

// 当前视图名（项目名 或 "全部项目"）
const scopeName = computed(() => {
  if (selectedProjectId.value) {
    const p = projects.value.find(p => p.id === selectedProjectId.value)
    return p?.name || '当前项目'
  }
  return '全部项目'
})

// 当前时间范围名
const periodName = computed(() => ({ '7d': '近 7 天', '30d': '近 30 天', '90d': '近 90 天' })[selectedPeriod.value] || '')

// --- Computed: Core metrics ---
const coreMetrics = computed(() => {
  if (!stats.value) return []
  const m = stats.value.core_metrics
  return [
    { label: '项目总数', value: m.total_projects, icon: 'assessment', iconColor: 'text-primary', trend: m.project_trend || 0 },
    { label: '已完成项目', value: m.completed_projects, icon: 'task_alt', iconColor: 'text-success-green', trend: m.completed_trend || 0 },
    { label: '平均完成度', value: m.avg_completion_rate + '%', icon: 'trending_up', iconColor: 'text-primary', trend: m.completion_trend || 0 },
    { label: '风险总数', value: m.total_risks, icon: 'warning', iconColor: 'text-warning-amber', trend: m.risk_trend || 0 },
  ]
})

// --- Computed: Status distribution ---
const statusDistribution = computed(() => {
  if (!stats.value) return []
  return stats.value.status_distribution
})

// --- Computed: Efficiency metrics ---
const efficiencyMetrics = computed(() => {
  if (!stats.value) return []
  const e = stats.value.efficiency_metrics
  return [
    { label: '平均准备时长', value: e.avg_prep_days + ' 天', icon: 'schedule', color: '#1a73e8', bgColor: 'rgba(26,115,232,0.1)' },
    { label: '平均审核时长', value: e.avg_review_days + ' 天', icon: 'rate_review', color: '#fbbc04', bgColor: 'rgba(251,188,4,0.1)' },
    { label: '合规通过率', value: e.compliance_rate + '%', icon: 'verified', color: '#34a853', bgColor: 'rgba(52,168,83,0.1)' },
    { label: '平均响应时间', value: e.avg_response_hours + ' 小时', icon: 'timer', color: '#ba1a1a', bgColor: 'rgba(186,26,26,0.1)' },
  ]
})

// --- Computed: Trend chart（M37：风险新增时间序列，按项目+时间窗口） ---
const trendChart = computed(() => {
  if (!stats.value) return []
  return stats.value.trend_chart
})

const maxTrendValue = computed(() => {
  if (!trendChart.value.length) return 10
  const max = Math.max(...trendChart.value.map(d => d.new_risks || 0))
  return Math.max(max, 10)
})

// --- Computed: Risk overview（M37：按当前项目实时汇总） ---
const pendingRisks = computed(() => stats.value?.risk_overview?.pending ?? stats.value?.core_metrics?.total_risks ?? 0)

// 等级卡数据：为后端字段补充 key/百分比兜底（percentage 可能四舍五入不足 100）
const riskLevels = computed(() => {
  const raw = stats.value?.risk_levels ?? []
  const keyMap = { 高风险: 'high', 中风险: 'medium', 低风险: 'low' }
  return raw.map(r => ({ ...r, key: keyMap[r.label] || 'low' }))
})

// 等级图标（Material Symbols）
function riskIcon(key) {
  return { high: 'local_fire_department', medium: 'warning_amber', low: 'info' }[key] || 'info'
}

// 构成条 ARIA 描述（可访问性）
const riskComposeAria = computed(() => {
  const parts = riskLevels.value.map(r => `${r.label} ${r.count} 项（${r.percentage}%）`)
  return `风险构成：${parts.join('，')}`
})

const pendingRequirements = computed(() => stats.value?.compliance?.pending_requirements ?? [])

// 兼容旧字段名（顶部"X 项待处理"沿用 totalRisks 名）
const totalRisks = pendingRisks

// --- Computed: Compliance ---
const totalItems = computed(() => stats.value?.compliance?.total_items || 0)
const passedItems = computed(() => stats.value?.compliance?.passed_items || 0)
const pendingItems = computed(() => stats.value?.compliance?.pending_items || 0)
const complianceScore = computed(() => stats.value?.compliance?.score || 0)

onMounted(async () => {
  await loadProjects()
  await loadStats()
})
</script>

<style scoped>
.analytics-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.page-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--on-surface);
  margin: 0;
}

.page-desc {
  font-size: 14px;
  color: var(--on-surface-variant);
  margin: 4px 0 0;
}

.update-time {
  font-size: 12px;
  color: var(--outline);
  font-style: normal;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.period-select {
  width: 140px;
}

/* M37：当前视图标识条（项目 + 时间维度联动） */
.scope-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--on-surface-variant);
  background: var(--surface-container-low);
  border: 1px solid var(--outline-variant);
  border-radius: 10px;
  padding: 8px 14px;
  margin-bottom: 16px;
}
.scope-banner .material-symbols-outlined { font-size: 18px; color: var(--primary); }
.scope-banner strong { color: var(--on-surface); }

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
  height: 120px;
  background: var(--surface-container);
  border-radius: 12px;
  animation: pulse 1.5s ease-in-out infinite;
}

.skeleton-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.skeleton-chart {
  height: 200px;
  background: var(--surface-container);
  border-radius: 12px;
  animation: pulse 1.5s ease-in-out infinite;
}

.skeleton-chart.large {
  height: 240px;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Metrics */
.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.metric-card {
  background: var(--surface-container-lowest);
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border-left: 4px solid var(--primary);
}

.metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.metric-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--on-surface-variant);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.metric-icon {
  font-size: 24px;
  padding: 8px;
  border-radius: 8px;
  background: var(--primary-fixed);
}

.metric-icon.text-primary { color: var(--primary); background: var(--primary-fixed); }
.metric-icon.text-success-green { color: #34a853; background: rgba(52,168,83,0.1); }
.metric-icon.text-warning-amber { color: #fbbc04; background: rgba(251,188,4,0.1); }

.metric-body {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.metric-value {
  font-size: 36px;
  font-weight: 700;
  color: var(--on-surface);
  letter-spacing: -0.02em;
}

.metric-trend {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 14px;
  font-weight: 600;
}

.metric-trend.up { color: #34a853; }
.metric-trend.down { color: #ba1a1a; }
.metric-trend.flat { color: var(--outline); }

.metric-trend .material-symbols-outlined {
  font-size: 16px;
}

.metric-footer {
  margin-top: 4px;
}

.metric-compare {
  font-size: 12px;
  color: var(--outline);
}

/* Charts */
.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.chart-card {
  background: var(--surface-container-lowest);
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  padding: 20px;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.chart-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--on-surface);
  margin: 0;
}

.chart-subtitle {
  font-size: 12px;
  color: var(--outline);
}

/* Status chart */
.status-chart {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.status-bar-item {
  display: grid;
  grid-template-columns: 100px 1fr 40px;
  align-items: center;
  gap: 12px;
}

.status-bar-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--on-surface-variant);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-bar-track {
  height: 8px;
  background: var(--surface-gray);
  border-radius: 4px;
  overflow: hidden;
}

.status-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s ease;
}

.status-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--on-surface);
  text-align: right;
}

/* Efficiency */
.efficiency-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.efficiency-item {
  display: grid;
  grid-template-columns: 40px 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--surface-gray);
  border-radius: 8px;
}

.efficiency-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.efficiency-icon .material-symbols-outlined {
  font-size: 24px;
}

.efficiency-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.efficiency-label {
  font-size: 12px;
  color: var(--on-surface-variant);
}

.efficiency-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--on-surface);
}

.efficiency-unit {
  font-size: 12px;
  color: var(--outline);
}

/* Trend chart */
.trend-card {
  background: var(--surface-container-lowest);
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  padding: 20px;
}

.legend-row {
  display: flex;
  gap: 16px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--on-surface-variant);
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.trend-chart {
  position: relative;
  height: 240px;
  display: flex;
  align-items: flex-end;
  padding-left: 40px;
}

.chart-grid {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  bottom: 30px;
}

.grid-line {
  position: absolute;
  left: 0;
  right: 0;
  border-top: 1px dashed var(--outline-variant);
}

.chart-bars {
  display: flex;
  width: 100%;
  justify-content: space-around;
  align-items: flex-end;
  height: 200px;
  padding-bottom: 30px;
  position: relative;
  z-index: 1;
}

.bar-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.bar-pair {
  display: flex;
  gap: 4px;
  align-items: flex-end;
  height: 160px;
}

.bar {
  width: 24px;
  border-radius: 4px 4px 0 0;
  transition: height 0.6s ease;
}

.bar-create { background: #1a73e8; }
.bar-complete { background: #34a853; }
.bar-risk { background: #ba1a1a; }

.bar-label {
  font-size: 11px;
  color: var(--outline);
}

/* Overview grid */
.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.overview-card {
  background: var(--surface-container-lowest);
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  padding: 20px;
}

.overview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.overview-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--on-surface);
  margin: 0;
}

.overview-badge {
  font-size: 12px;
  font-weight: 600;
  color: var(--error);
  background: var(--error-container);
  padding: 4px 8px;
  border-radius: 4px;
}

/* 方案 A：等级卡 + 构成条（替代旧 risk-level-row 平铺） */
.risk-badge-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: 999px;
  padding: 4px 12px;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.risk-badge-pill.has-risk {
  color: var(--error);
  background: var(--error-container);
}
.risk-badge-pill:not(.has-risk) {
  color: var(--success-green, #34a853);
  background: rgba(52, 168, 83, 0.1);
}
.risk-badge-icon { font-size: 15px; }

.risk-card-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}
.risk-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 14px 8px 12px;
  border-radius: 12px;
  border-left: 3px solid;
  background: var(--surface-container-low);
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.25s ease;
}
.risk-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}
.risk-card-high { border-color: #ba1a1a; background: rgba(186, 26, 26, 0.08); }
.risk-card-medium { border-color: #fbbc04; background: rgba(251, 188, 4, 0.08); }
.risk-card-low { border-color: #34a853; background: rgba(52, 168, 83, 0.08); }

.risk-card-icon { font-size: 20px; margin-bottom: 4px; }
.risk-card-high .risk-card-icon { color: #ba1a1a; }
.risk-card-medium .risk-card-icon { color: #b98900; }
.risk-card-low .risk-card-icon { color: #286c00; }

.risk-card-num {
  font-size: 32px;
  font-weight: 700;
  line-height: 1.1;
  color: var(--on-surface);
}
.risk-card-label { font-size: 12px; color: var(--on-surface-variant); }

/* 构成条 */
.risk-compose-bar {
  display: flex;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--surface-gray, rgba(0, 0, 0, 0.06));
  margin-bottom: 8px;
}
.risk-compose-seg {
  height: 100%;
  transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
.risk-compose-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.risk-compose-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--on-surface-variant);
}
.risk-compose-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

@media (max-width: 640px) {
  .risk-card-grid { grid-template-columns: 1fr; }
}

/* Compliance */
.compliance-score {
  font-size: 24px;
  font-weight: 700;
  color: var(--primary);
}

.compliance-body {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 24px;
  align-items: center;
}

.compliance-ring {
  position: relative;
  width: 120px;
  height: 120px;
}

.ring-chart {
  width: 100%;
  height: 100%;
}

.ring-bg {
  fill: none;
  stroke: var(--surface-gray);
  stroke-width: 3;
}

.ring-progress {
  fill: none;
  stroke: var(--primary);
  stroke-width: 3;
  stroke-linecap: round;
  transition: stroke-dasharray 0.6s ease;
}

.ring-label {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.ring-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--primary);
}

.ring-text {
  font-size: 10px;
  color: var(--outline);
  text-transform: uppercase;
}

.compliance-stats {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.compliance-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.compliance-stat .stat-num {
  font-size: 20px;
  font-weight: 700;
  color: var(--on-surface);
}

.compliance-stat .stat-label {
  font-size: 12px;
  color: var(--outline);
}

/* M37：未达标项清单 */
.compliance-pending {
  margin-top: 12px;
  border-top: 1px dashed var(--outline-variant);
  padding-top: 10px;
}
.pending-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--on-surface-variant);
  margin-bottom: 6px;
}
.pending-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--on-surface-variant);
  padding: 4px 6px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}
.pending-item:hover {
  background: var(--surface-container-low);
}
.pending-item:hover .pending-link {
  color: var(--primary);
  opacity: 1;
}
.pending-item .pending-icon { font-size: 15px; color: var(--error, #ba1a1a); flex-shrink: 0; }
.pending-item .pending-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pending-project {
  flex-shrink: 0;
}
.pending-link {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--primary);
  opacity: 0.7;
}

/* Empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 32px;
  background: white;
  border: 1px dashed var(--outline-variant);
  border-radius: 16px;
  text-align: center;
}

.empty-state .material-symbols-outlined {
  font-size: 64px;
  color: var(--outline);
  margin-bottom: 16px;
}

.empty-state h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--on-surface);
  margin-bottom: 8px;
}

.empty-state p {
  font-size: 14px;
  color: var(--on-surface-variant);
}

/* Responsive */
@media (max-width: 1200px) {
  .metrics-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .charts-grid,
  .overview-grid {
    grid-template-columns: 1fr;
  }
  .compliance-body {
    grid-template-columns: 1fr;
    text-align: center;
  }
  .skeleton-cards {
    grid-template-columns: repeat(2, 1fr);
  }
  .skeleton-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .metrics-row {
    grid-template-columns: 1fr;
  }
  .page-header {
    flex-direction: column;
    gap: 12px;
  }
}

/* Utility */
.text-primary { color: var(--primary); }
.text-success-green { color: #34a853; }
.text-warning-amber { color: #fbbc04; }
</style>