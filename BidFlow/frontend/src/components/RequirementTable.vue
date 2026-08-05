<!-- RequirementTable.vue - Requirement management with match analysis and batch operations -->
<template>
  <div class="requirement-table">
    <!-- Action bar -->
    <div class="action-bar">
      <div class="action-left">
        <el-button type="primary" size="default" :loading="analyzing" @click="handleAnalyzeMatch">
          <template #icon><span class="material-symbols-outlined">analytics</span></template>
          匹配分析
        </el-button>
        <el-button size="default" :loading="batchGenerating" @click="handleBatchGenerate" :disabled="!requirements.length">
          <template #icon><span class="material-symbols-outlined">tips_and_updates</span></template>
          批量生成响应
        </el-button>
      </div>
      <div class="action-right" v-if="matchSummary">
        <span class="match-stat">
          匹配率: <strong>{{ matchSummary.match_rate }}%</strong>
        </span>
        <span class="match-stat matched">
          已匹配: <strong>{{ matchSummary.matched }}</strong>
        </span>
        <span class="match-stat unmatched">
          未匹配: <strong>{{ matchSummary.unmatched }}</strong>
        </span>
      </div>
    </div>

    <!-- Filter header -->
    <div class="filter-bar">
      <div class="filter-group">
        <label>类别</label>
        <el-select v-model="filters.category" placeholder="全部" clearable style="width: 140px">
          <el-option label="全部" value="" />
          <el-option label="资格" value="资格" />
          <el-option label="商务" value="商务" />
          <el-option label="技术" value="技术" />
          <el-option label="评分" value="评分" />
        </el-select>
      </div>
      <div class="filter-group">
        <label>匹配状态</label>
        <el-select v-model="filters.matchStatus" placeholder="全部" clearable style="width: 120px">
          <el-option label="全部" value="" />
          <el-option label="已匹配" value="matched" />
          <el-option label="未匹配" value="unmatched" />
        </el-select>
      </div>
      <div class="filter-group">
        <label>优先级</label>
        <el-select v-model="filters.priority" placeholder="全部" clearable style="width: 100px">
          <el-option label="全部" value="" />
          <el-option label="P0" value="p0" />
          <el-option label="P1" value="p1" />
          <el-option label="P2" value="p2" />
        </el-select>
      </div>
      <div class="filter-group filter-search">
        <label>关键词</label>
        <el-input v-model="filters.keyword" placeholder="搜索需求内容..." clearable />
      </div>
    </div>

    <!-- Table -->
    <el-table
      :data="filteredRequirements"
      v-loading="loading"
      class="req-table"
      @selection-change="handleSelectionChange"
      :header-cell-style="{ background: '#f7f9fc', color: '#414754', fontWeight: 'bold' }"
    >
      <el-table-column type="selection" width="48" align="center" />

      <el-table-column label="编号" width="64" align="center">
        <template #default="scope">{{ String(scope.$index + 1).padStart(3, '0') }}</template>
      </el-table-column>

      <el-table-column label="类别" width="100">
        <template #default="scope">
          <el-tag :type="getCategoryType(scope.row.category)" effect="light" size="small">
            {{ getCategoryLabel(scope.row.category) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="需求内容" min-width="280">
        <template #default="scope">
          <div class="req-content">
            <p>{{ scope.row.content || scope.row.title || '--' }}</p>
            <p v-if="scope.row.description" class="req-desc">{{ scope.row.description }}</p>
            <p v-if="!scope.row.content && scope.row.title" class="req-desc">{{ scope.row.source_text || '' }}</p>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="匹配状态" width="140" align="center">
        <template #default="scope">
          <div v-if="getMatchInfo(scope.row)" class="match-cell">
            <el-tooltip v-if="getMatchInfo(scope.row).has_match" placement="top">
              <template #content>
                <div v-if="getMatchInfo(scope.row).matched_sources?.length">
                  <div v-for="(src, i) in getMatchInfo(scope.row).matched_sources" :key="i">
                    📄 {{ src.filename }} (得分: {{ src.score?.toFixed(1) || 0 }})
                  </div>
                </div>
                <span v-else>匹配到 {{ getMatchInfo(scope.row).match_count }} 条资料</span>
              </template>
              <el-tag type="success" size="small" effect="light" class="match-tag matched">
                <span class="match-icon">✓</span> 已匹配 ({{ getMatchInfo(scope.row).match_count }})
              </el-tag>
            </el-tooltip>
            <el-tooltip v-else placement="top" content="企业资料库中暂无相关资料，建议上传更多企业文档">
              <el-tag type="info" size="small" effect="light" class="match-tag unmatched">
                <span class="match-icon">✗</span> 未匹配
              </el-tag>
            </el-tooltip>
          </div>
          <span v-else class="match-placeholder">-</span>
        </template>
      </el-table-column>

      <el-table-column label="响应状态" width="110" align="center">
        <template #default="scope">
          <el-tooltip v-if="scope.row.has_response || getMatchInfo(scope.row)?.has_response" placement="top" content="已生成响应草稿">
            <el-tag :type="getResponseTagType(getResponseStatus(scope.row))" size="small" effect="light">
              {{ getResponseStatusLabel(getResponseStatus(scope.row)) }}
            </el-tag>
          </el-tooltip>
          <el-tag v-else type="info" size="small" effect="plain">未生成</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="优先级" width="80" align="center">
        <template #default="scope">
          <span :class="['priority-badge', scope.row.priority]">
            <span class="priority-dot" :class="scope.row.priority"></span>
            {{ scope.row.priority }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="风险" width="86" min-width="86" align="center">
        <template #default="scope">
          <el-tag v-if="scope.row.risk_level === '高'" type="danger" size="small" effect="light">高</el-tag>
          <el-tag v-else-if="scope.row.risk_level === '中'" type="warning" size="small" effect="light">中</el-tag>
          <el-tag v-else-if="scope.row.risk_level === '低'" type="success" size="small" effect="light">低</el-tag>
          <span v-else class="no-risk">-</span>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="140" align="center" fixed="right">
        <template #default="scope">
          <div class="action-btns">
            <el-button size="small" type="primary" link @click="emit('generate-draft', scope.row.id)" title="AI 生成草案">
              <span class="material-symbols-outlined">tips_and_updates</span>
            </el-button>
            <el-button size="small" type="primary" link @click="emit('edit', scope.row)" title="编辑需求">
              <span class="material-symbols-outlined">edit</span>
            </el-button>
            <el-button size="small" type="primary" link @click="emit('view', scope.row)" title="查看详情">
              <span class="material-symbols-outlined">visibility</span>
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- Empty state -->
    <el-empty v-if="filteredRequirements.length === 0 && !loading" description="未找到符合条件的需求" />

    <!-- Selection bar -->
    <div v-if="selected.length > 0" class="selection-bar">
      <span>已选中 <strong>{{ selected.length }}</strong> 项</span>
      <el-button size="small" type="primary" @click="handleBatchGenerateSelected" :loading="batchGenerating">批量生成响应</el-button>
      <el-button size="small" type="danger" @click="handleBatchDelete">批量删除</el-button>
    </div>

    <!-- Footer stats -->
    <div class="table-footer">
      <div class="footer-stats">
        <span>总计: <strong>{{ requirements.length }}</strong></span>
        <span>已完成: <strong class="text-success-green">{{ doneCount }}</strong></span>
        <span>待处理: <strong class="text-warning-amber">{{ pendingCount }}</strong></span>
        <span v-if="matchSummary">已匹配: <strong class="text-primary">{{ matchSummary.matched }}</strong></span>
      </div>
      <span class="footer-page">共 {{ Math.ceil(requirements.length / 20) }} 页</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { analyzeMatches as analyzeMatchesApi, batchGenerateResponses as batchGenerateResponsesApi, getBatchStatus as getBatchStatusApi, pollMatchAnalysisTask } from '@/api/compliance'
import { parseResponse } from '@/utils/api'

const props = defineProps({
  requirements: { type: Array, default: () => [] },
  projectId: { type: [Number, String], default: null }
})

const emit = defineEmits(['generate-draft', 'edit', 'view', 'batch-delete', 'batch-generate-done'])

const filters = ref({
  category: '',
  priority: '',
  keyword: '',
  matchStatus: ''
})

const loading = ref(false)
const analyzing = ref(false)
const batchGenerating = ref(false)
const selected = ref([])
const matchData = ref(null)

// M7：轮询 AbortController——组件卸载时中止比对轮询
let matchPollCtrl = null

const matchSummary = computed(() => matchData.value?.summary || null)

const filteredRequirements = computed(() => {
  return props.requirements.filter(r => {
    // L7：类别归一化比较（筛选项为中文，后端/AI 可能返回英文 technical/business 等）
    if (filters.value.category) {
      const catMap = { 技术: 'technical', 商务: 'business', 资格: 'qualification', 评分: 'scoring' }
      const want = catMap[filters.value.category] || filters.value.category
      const got = catMap[r.category] || r.category
      if (want !== got && filters.value.category !== r.category) return false
    }
    if (filters.value.priority && r.priority !== filters.value.priority) return false
    if (filters.value.matchStatus) {
      const matchInfo = getMatchInfo(r)
      const isMatched = matchInfo?.has_match
      if (filters.value.matchStatus === 'matched' && !isMatched) return false
      if (filters.value.matchStatus === 'unmatched' && isMatched) return false
    }
    if (filters.value.keyword) {
      const kw = filters.value.keyword.toLowerCase()
      const searchText = (r.content || r.title || r.source_text || '').toLowerCase()
      if (!searchText.includes(kw)) return false
    }
    return true
  })
})

const doneCount = computed(() => props.requirements.filter(r => r.status === '已完成' || r.status === 'done').length)
const pendingCount = computed(() => props.requirements.filter(r => r.status === '待处理' || r.status === '待评审' || r.status === 'pending' || r.status === 'review').length)

function getMatchInfo(row) {
  if (!matchData.value?.matches) return null
  return matchData.value.matches.find(m => m.requirement_id === row.id)
}

function getResponseStatus(row) {
  // 优先使用需求自身的响应状态（来自后端 requirements 接口），回退到比对数据
  return row.response_status || getMatchInfo(row)?.response_status || null
}

function getResponseTagType(status) {
  const map = {
    'completed': 'success',
    'pending_review': 'warning',
    'needs_manual': 'info',
    'pending': 'info',
    '草稿': 'info',
    'editing': 'info',
    'review': 'warning',
    'approved': 'success',
    'rejected': 'danger',
  }
  return map[status] || 'info'
}

function getResponseStatusLabel(status) {
  const map = {
    'completed': '已完成',
    'pending_review': '待评审',
    'needs_manual': '需人工',
    'pending': '待处理',
    '草稿': '草稿',
    'editing': '待编辑',
    'review': '待审核',
    'approved': '已批准',
    'rejected': '已驳回',
  }
  return map[status] || '待处理'
}

function handleSelectionChange(items) {
  selected.value = items
}

async function handleAnalyzeMatch() {
  if (!props.projectId) {
    ElMessage.warning('项目ID不存在')
    return
  }
  await loadMatchAnalysis({ notifyOnError: true })  // 按钮场景失败需提示用户
}

/**
 * 通用：从后端加载比对分析结果写入 matchData。
 *  - 无历史 → GET 返回 task_id → 后台异步跑 → 共享轮询直到 completed
 *  - 有历史 → GET 直接返回完整数据 → 立即写入
 *  - 0 需求短路 → GET 返回 {summary:{total:0...}} → 立即写入
 *
 * 供「用户点按钮」和「组件挂载/projectId 变化自动加载」共用
 */
async function loadMatchAnalysis({ notifyOnError = false } = {}) {
  loading.value = true   // M11：同步驱动表格 v-loading（之前绑定值从未置位）
  analyzing.value = true
  try {
    const res = await analyzeMatchesApi(props.projectId)
    const data = parseResponse(res, null)
    if (data?.task_id && data?.status === 'running') {
      // 后端无历史 + 有需求 → 异步计算中，轮询等完成（M7：传 signal 支持卸载中止）
      matchPollCtrl?.abort()
      matchPollCtrl = new AbortController()
      const finalData = await pollMatchAnalysisTask(props.projectId, data.task_id, { signal: matchPollCtrl.signal })
      matchData.value = finalData
      if (finalData?.summary) {
        ElMessage.success(`分析完成: 匹配率 ${finalData.summary.match_rate}%`)
      }
    } else {
      // 有历史 或 0 需求短路 → 立即可显示
      matchData.value = data
      if (data?.summary) {
        ElMessage.success(`分析完成: 匹配率 ${data.summary.match_rate}%`)
      }
    }
  } catch (e) {
    console.warn('[RequirementTable] 加载比对分析失败：', e)
    // 自动加载失败不打扰；用户主动点击（按钮场景）才提示
    if (notifyOnError) ElMessage.error('比对分析失败，请稍后重试')
  } finally {
    loading.value = false
    analyzing.value = false
  }
}

// 进入项目/项目 ID 变化 → 自动从后端持久化层恢复历史 match_analysis_runs
onMounted(() => {
  if (props.projectId) loadMatchAnalysis()
})
watch(() => props.projectId, (id) => {
  if (id) loadMatchAnalysis()
})
// M7：组件卸载时中止轮询，避免定时器泄漏
onUnmounted(() => {
  matchPollCtrl?.abort()
})

async function handleBatchGenerate(ids = null) {
  if (!props.projectId) {
    ElMessage.warning('项目ID不存在')
    return
  }
  try {
    await ElMessageBox.confirm(
      ids?.length
        ? `确定为选中的 ${ids.length} 条需求批量生成AI响应吗？此操作会调用AI服务，可能需要一些时间。`
        : '确定要为所有需求批量生成AI响应吗？此操作会调用AI服务，可能需要一些时间。',
      '批量生成确认',
      { confirmButtonText: '确认生成', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }

  batchGenerating.value = true
  let pollTimer = null
  try {
    // 1. 启动任务（立即返回 task_id）
    const startRes = await batchGenerateResponsesApi(props.projectId, ids)
    const startData = parseResponse(startRes, {})

    if (!startData.task_id) {
      ElMessage.info(startData.message || '没有待处理的已匹配需求')
      return
    }

    const taskId = startData.task_id
    const total = startData.total || 0
    ElMessage.info(`批量生成任务已启动，共 ${total} 项，正在后台处理...`)

    // 2. 每 2s 轮询进度（复用 ProjectDetailView 的异步模式）
    await new Promise((resolve, reject) => {
      pollTimer = setInterval(async () => {
        try {
          const statusRes = await getBatchStatusApi(props.projectId, taskId)
          const status = parseResponse(statusRes, {})
          if (status.status === 'completed' || status.status === 'failed') {
            clearInterval(pollTimer)
            pollTimer = null
            if (status.status === 'failed') {
              reject(new Error(status.error || '批量任务执行失败'))
            } else {
              resolve(status)
            }
          }
        } catch (err) {
          clearInterval(pollTimer)
          pollTimer = null
          reject(err)
        }
      }, 2000)
    })

    // 3. 完成：读取最终状态（与后端字段契约一致：succeeded/skipped/failed）
    const statusRes = await getBatchStatusApi(props.projectId, taskId)
    const finalStatus = parseResponse(statusRes, {}) || {}
    const { succeeded = 0, skipped = 0, failed = 0 } = finalStatus
    ElMessage.success(`生成完成: 成功 ${succeeded} 项，跳过 ${skipped} 项${failed ? `，失败 ${failed} 项` : ''}`)
    emit('batch-generate-done', finalStatus)
  } catch (e) {
    ElMessage.error(e.message || '批量生成失败')
  } finally {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    batchGenerating.value = false
  }
}

async function handleBatchGenerateSelected() {
  if (!props.projectId || !selected.value.length) return
  // H3 修复：传入选中的需求 ID，后端只处理这些（不再全项目生成）
  await handleBatchGenerate(selected.value.map(r => r.id))
}

function getCategoryType(cat) {
  const map = { 技术: 'primary', 商务: '', 资格: 'info', 评分: 'warning' }
  return map[cat] || ''
}

function getCategoryLabel(cat) {
  return cat || '其他'
}

async function handleBatchDelete() {
  if (!selected.value.length) return
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selected.value.length} 项需求吗？此操作无法撤销。`,
      '确认批量删除',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' }
    )
    emit('batch-delete', selected.value.map(r => r.id))
    selected.value = []
  } catch {
    // 用户取消
  }
}

// 暴露给父组件（修复弹窗/列表匹配数据不一致：handleViewRequirement 通过 ref 取本组件 matchData，保证数据源统一）
defineExpose({
  getMatchInfo,
  loadMatchAnalysis,
})
</script>

<style scoped>
.requirement-table {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Action bar */
.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f8fafc 0%, #eef2f7 100%);
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
}

.action-left {
  display: flex;
  gap: 12px;
}

.action-right {
  display: flex;
  gap: 20px;
}

.match-stat {
  font-size: 13px;
  color: var(--on-surface-variant);
}

.match-stat strong {
  color: var(--primary);
  font-size: 15px;
}

.match-stat.matched strong {
  color: #34a853;
}

.match-stat.unmatched strong {
  color: #ea4335;
}

/* Filter bar */
.filter-bar {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
  padding: 16px;
  background: white;
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.filter-group label {
  font-size: 11px;
  color: var(--on-surface-variant);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.filter-search {
  flex: 1;
  min-width: 200px;
}

/* Table */
.req-table :deep(.el-table__row:hover) {
  background: var(--surface-container-low) !important;
}

.req-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.req-content p {
  font-size: 14px;
  color: var(--on-surface);
  margin: 0;
  /* 2 行截断：长需求内容不撑高表格行，完整内容在「查看详情」弹窗展示 */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.req-desc {
  font-size: 12px;
  color: var(--on-surface-variant);
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Match cell */
.match-cell {
  display: flex;
  justify-content: center;
}

.match-tag {
  font-size: 12px;
  font-weight: 600;
}

.match-tag.matched {
  background: rgba(52, 168, 83, 0.1);
  border-color: #34a853;
}

.match-tag.unmatched {
  background: rgba(234, 67, 53, 0.1);
  border-color: #ea4335;
}

.match-icon {
  margin-right: 2px;
}

.match-placeholder {
  color: var(--outline);
  font-size: 12px;
}

.priority-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 700;
  font-size: 13px;
}

.priority-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.priority-dot.p0 { background: var(--error); }
.priority-dot.p1 { background: #fbbc04; }
.priority-dot.p2 { background: var(--outline); }

.no-risk {
  color: var(--outline);
  font-size: 13px;
}

.action-btns {
  display: flex;
  gap: 6px;
  justify-content: center;
  padding-left: 12px;  /* 与「风险」列强制视觉间隔，避免 el-tag 覆盖 */
}

/* Selection bar */
.selection-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  background: rgba(26, 115, 232, 0.1);
  border-bottom: 1px solid rgba(26, 115, 232, 0.2);
  font-size: 14px;
}

/* Footer */
.table-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-top: 1px solid var(--outline-variant);
  background: var(--surface-container-low);
}

.footer-stats {
  display: flex;
  gap: 24px;
  font-size: 14px;
}

.footer-stats strong {
  font-weight: 700;
}

.footer-page {
  font-size: 13px;
  color: var(--outline);
}

.text-success-green { color: #34a853; }
.text-warning-amber { color: #fbbc04; }
.text-primary { color: var(--primary); }
</style>