<!-- ProjectDetailView.vue - Project detail with tabs for documents, requirements, compliance -->
<template>
  <div class="project-detail" v-loading="projectStore.loading">
    <!-- Project header card -->
    <div class="project-header">
      <div class="header-top">
        <div class="header-left">
          <div class="header-title-row">
            <h1>{{ projectStore.currentProject?.name || '加载中...' }}</h1>
            <el-tag v-if="projectStore.currentProject?.status" :type="getStatusType(projectStore.currentProject.status)" effect="light" class="status-tag">
              {{ projectStore.currentProject.status }}
            </el-tag>
          </div>
          <p class="header-meta">
            <span class="material-symbols-outlined">business</span>
            {{ projectStore.currentProject?.tenderer || '招标单位' }}
          </p>
        </div>
        <div class="header-right-info">
          <span class="deadline-label">投标截止日期</span>
          <span class="deadline-value">
            <span class="material-symbols-outlined">event</span>
            {{ formatDate(projectStore.currentProject?.deadline) }}
          </span>
        </div>
      </div>

      <div class="header-bottom">
        <div class="progress-section">
          <div class="progress-header">
            <span>响应就绪度</span>
            <span class="progress-pct">{{ readiness?.overall ?? projectStore.currentProject?.completionRate ?? 0 }}%</span>
          </div>
          <el-progress :percentage="readiness?.overall ?? projectStore.currentProject?.completionRate ?? 0" :stroke-width="10" />
          <div class="readiness-breakdown" v-if="readiness">
            <span class="breakdown-tag">基础 {{ readiness.base_rate }}%</span>
            <span class="breakdown-tag">引用 {{ readiness.quality_rate }}%</span>
            <span class="breakdown-tag">合规 {{ readiness.compliance_rate }}%</span>
            <span v-if="(readiness.total_risk_pending ?? readiness.high_risk_pending) > 0" class="risk-tag">待处理风险 {{ readiness.total_risk_pending ?? readiness.high_risk_pending }}</span>
          </div>
        </div>
        <div class="header-actions">
          <el-button size="small" @click="exportDraft" class="export-btn">导出草稿</el-button>
          <!-- 标书导出：合并全部需求响应生成投标文件（Markdown/PDF）——就绪度 ≥95% 且无未处理高风险才放行 -->
          <el-tooltip :content="exportBlockReason || '导出投标响应文件'" placement="top" :disabled="canExportBid">
            <el-dropdown trigger="click" @command="exportBidDocument" :disabled="!canExportBid">
              <el-button size="small" type="primary" plain class="export-btn" :disabled="!canExportBid">导出标书</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="markdown">Markdown 文档</el-dropdown-item>
                  <el-dropdown-item command="pdf">PDF 文档</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </el-tooltip>
          <!-- 方案 A：一键打包投递包（标书 md/pdf + 合规报告 md/pdf + README）——同样受就绪度门槛约束 -->
          <el-tooltip :content="exportBlockReason || '打包全部投递文件'" placement="top" :disabled="canExportBid">
            <el-button size="small" type="primary" class="submit-btn" @click="exportBidPackage" :loading="packaging" :disabled="!canExportBid">
              <template #icon><span class="material-symbols-outlined">archive</span></template>
              打包投递包
            </el-button>
          </el-tooltip>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="tab-container">
      <div class="tab-headers">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="['tab-btn', { active: activeTab === tab.key }]"
          @click="activeTab = tab.key"
        >
          <span class="material-symbols-outlined">{{ tab.icon }}</span>
          {{ tab.label }}
        </button>
      </div>

      <!-- Tab: Tender Documents -->
      <div v-show="activeTab === 'tender'" class="tab-content">
        <div class="tender-layout">
          <div class="upload-panel">
            <h3>文档管理</h3>
            <div class="upload-zone">
              <el-upload
                drag
                :auto-upload="false"
                :on-change="handleFileChange"
                multiple
                accept=".pdf,.docx,.txt"
                class="upload-dragger"
              >
                <span class="material-symbols-outlined upload-icon">cloud_upload</span>
                <p class="upload-title">点击或拖拽文件进行上传</p>
                <p class="upload-hint">支持格式：PDF, DOCX, TXT (限 25MB)</p>
              </el-upload>
            </div>
            <div class="file-list">
              <div v-for="file in tenderDocs" :key="file.id" class="file-item">
                <div class="file-done">
                  <span class="material-symbols-outlined" :class="isTenderDocSuccess(file.status) ? 'text-success-green' : 'text-primary'">
                    {{ isTenderDocSuccess(file.status) ? 'check_circle' : 'article' }}
                  </span>
                  <span class="file-name">{{ file.filename }}</span>
                  <el-dropdown>
                    <button class="file-more">
                      <span class="material-symbols-outlined text-[18px]">more_vert</span>
                    </button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item @click="handleDeleteDoc(file.id)">删除</el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </div>
              <div v-if="!tenderDocs.length" class="empty-files">
                <span class="material-symbols-outlined">upload_file</span>
                <p>暂无上传文件</p>
              </div>
            </div>
          </div>

          <div class="analysis-panel">
            <div class="analysis-header">
              <h3>
                <span class="material-symbols-outlined text-primary">psychology</span>
                AI 提取需求
              </h3>
              <el-tag type="primary" effect="light" class="req-count">已识别 {{ requirements.length }} 项需求</el-tag>
            </div>

            <div class="analysis-content">
              <section class="analysis-section">
                <h4>基础信息</h4>
                <div class="info-grid">
                  <div class="info-item">
                    <span class="info-label">招标文件编号</span>
                    <span class="info-value">{{ projectStore.currentProject?.tender_ref_no || projectStore.currentProject?.tender_no || projectStore.currentProject?.id || '--' }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">项目总预算</span>
                    <span class="info-value">{{ projectStore.currentProject?.budget ? `¥${projectStore.currentProject.budget}万` : '--' }}</span>
                  </div>
                </div>
              </section>

              <section class="analysis-section">
                <h4>资质要求</h4>
                <div v-if="requirements.length" class="req-list">
                  <div v-for="req in requirements.slice(0, 3)" :key="req.id" class="req-card ai-accent">
                    <div class="req-header">
                      <span class="req-title">{{ req.title || req.content?.substring(0, 40) || '--' }}</span>
                      <span class="priority-tag" :class="getPriorityClass(req.priority)">
                        {{ getPriorityLabel(req.priority) }}
                      </span>
                    </div>
                    <p class="req-desc">{{ req.content?.substring(0, 120) || req.description || '暂无内容' }}</p>
                    <p class="req-source" v-if="req.source_ref">— {{ req.source_ref }}</p>
                  </div>
                </div>
                <div v-else class="empty-req">
                  <span class="material-symbols-outlined">description</span>
                  <p>上传招标文件后，AI 将自动提取关键需求</p>
                </div>
              </section>

              <section class="analysis-section">
                <h4>技术要求</h4>
                <div v-if="technicalRequirements.length" class="req-list">
                  <div v-for="(tech, i) in technicalRequirements" :key="i" class="tech-card">
                    <p class="tech-content">{{ tech.content }}</p>
                    <div class="tech-tags" v-if="tech.tags?.length">
                      <span v-for="(tag, j) in tech.tags" :key="j" class="tech-tag">{{ tag }}</span>
                    </div>
                  </div>
                </div>
                <div v-else class="empty-req">
                  <span class="material-symbols-outlined">build</span>
                  <p>暂无技术要求，上传招标文件后将自动识别</p>
                </div>
              </section>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab: Response Checklist -->
      <div v-show="activeTab === 'response'" class="tab-content">
        <div class="empty-state-card" v-if="!requirements.length">
          <span class="material-symbols-outlined empty-icon">checklist_rtl</span>
          <h3>结构化响应矩阵</h3>
          <p>此视图将显示从招标文件分析中生成的逐项响应提示。请先在「招标文件」页上传并解析文档，生成需求清单。</p>
        </div>
        <RequirementTable
          v-else
          ref="requirementTableRef"
          :requirements="requirements"
          :projectId="projectId"
          @generate-draft="handleGenerateDraft"
          @edit="handleEditRequirement"
          @view="handleViewRequirement"
          @batch-delete="handleBatchDeleteRequirements"
          @batch-generate-done="loadRequirements"
        />
      </div>

      <!-- Tab: 比对分析 -->
      <div v-show="activeTab === 'comparison'" class="tab-content">
        <div class="comparison-layout">
          <!-- 左侧：比对汇总 -->
          <div class="comparison-sidebar">
            <div class="comparison-summary">
              <h3>比对汇总</h3>
              <div class="summary-cards" v-if="comparisonData">
                <div class="summary-card total">
                  <span class="summary-value">{{ comparisonData.summary.total }}</span>
                  <span class="summary-label">需求总数</span>
                </div>
                <div class="summary-card matched">
                  <span class="summary-value">{{ comparisonData.summary.matched }}</span>
                  <span class="summary-label">已匹配</span>
                </div>
                <div class="summary-card unmatched">
                  <span class="summary-value">{{ comparisonData.summary.unmatched }}</span>
                  <span class="summary-label">未匹配</span>
                </div>
                <div class="summary-card rate">
                  <span class="summary-value">{{ comparisonData.summary.match_rate }}%</span>
                  <span class="summary-label">匹配率</span>
                </div>
              </div>
              <div v-else class="summary-empty">
                <span class="material-symbols-outlined">analytics</span>
                <p>点击「开始比对分析」生成比对结果</p>
              </div>
              <div v-if="comparisonData?.last_analyzed_at" class="summary-meta">
                <span class="material-symbols-outlined">schedule</span>
                上次分析：{{ formatLastAnalyzed(comparisonData.last_analyzed_at) }}
              </div>
              <el-button
                type="primary"
                :loading="comparing"
                @click="runComparison"
                class="comparison-btn"
              >
                <template #icon><span class="material-symbols-outlined">search</span></template>
                {{ comparisonData ? '重新比对' : '开始比对分析' }}
              </el-button>
            </div>

            <!-- 状态分布 -->
            <div class="comparison-stats" v-if="comparisonData">
              <h4>需求分类统计</h4>
              <div class="stats-list">
                <div class="stats-item">
                  <span>技术类需求</span>
                  <strong>{{ categoryCount('技术') }}</strong>
                </div>
                <div class="stats-item">
                  <span>商务类需求</span>
                  <strong>{{ categoryCount('商务') }}</strong>
                </div>
                <div class="stats-item">
                  <span>资格类需求</span>
                  <strong>{{ categoryCount('资格') }}</strong>
                </div>
              </div>
            </div>
          </div>

          <!-- 右侧：逐条比对详情 -->
          <div class="comparison-detail">
            <div class="detail-header">
              <h3>逐条比对详情</h3>
              <div class="detail-actions" v-if="comparisonData">
                <el-button size="small" @click="filterComparison('all')" :class="{active: comparisonFilter === 'all'}">全部</el-button>
                <el-button size="small" @click="filterComparison('matched')" :class="{active: comparisonFilter === 'matched'}">已匹配</el-button>
                <el-button size="small" @click="filterComparison('unmatched')" :class="{active: comparisonFilter === 'unmatched'}">未匹配</el-button>
              </div>
            </div>

            <!-- 比对结果列表 -->
            <div class="comparison-list" v-if="comparisonData">
              <div
                v-for="match in pagedComparisonMatches"
                :key="match.requirement_id"
                class="comparison-item"
                :class="{ matched: match.has_match, unmatched: !match.has_match }"
              >
                <div class="item-header">
                  <div class="item-title">
                    <span class="item-id">#{{ match.requirement_id }}</span>
                    <el-tag :type="getCategoryTagType(match.category)" size="small" effect="light">
                      {{ match.category || '未分类' }}
                    </el-tag>
                    <span class="priority-indicator" :class="match.priority?.toLowerCase()">
                      {{ match.priority }}
                    </span>
                  </div>
                  <el-tag
                    :type="match.has_match ? 'success' : 'info'"
                    effect="light"
                    size="small"
                  >
                    {{ match.has_match ? '✓ 已匹配' : '✗ 未匹配' }}
                    <span v-if="match.has_match">({{ match.match_count }})</span>
                  </el-tag>
                </div>

                <div class="item-content">
                  <div class="content-row">
                    <span class="content-label">需求：</span>
                    <span class="content-text">{{ match.content }}</span>
                  </div>
                  <div class="content-row" v-if="match.has_match && match.matched_sources?.length">
                    <span class="content-label">匹配来源：</span>
                    <div class="source-list">
                      <div v-for="(src, idx) in match.matched_sources" :key="idx" class="source-item">
                        <div class="source-header">
                          <span class="source-filename">📄 {{ src.filename }}</span>
                          <el-tag size="small" :type="getScoreTagType(src.score)" effect="plain">
                            相似度: {{ src.score?.toFixed(1) || 0 }}
                          </el-tag>
                        </div>
                        <p class="source-preview">{{ src.content_preview }}</p>
                      </div>
                    </div>
                  </div>
                  <div class="content-row no-match" v-else>
                    <span class="no-match-hint">⚠ 企业资料库中暂无相关资料，建议在「企业资料」页面上传更多相关文档</span>
                  </div>
                </div>

                <div class="item-actions">
                  <el-button
                    v-if="match.has_match && !match.has_response"
                    type="primary"
                    size="small"
                    @click="generateSingleResponse(match.requirement_id)"
                  >
                    生成响应
                  </el-button>
                  <el-tag v-else-if="match.has_response" type="success" size="small" effect="light">
                    {{ getResponseStatusLabel(match.response_status) }}
                  </el-tag>
                  <el-button size="small" link @click="handleViewRequirement({id: match.requirement_id, content: match.content})">
                    查看详情
                  </el-button>
                </div>
              </div>
            </div>

            <!-- 空状态 -->
            <div class="comparison-empty" v-else>
              <div v-if="comparing" class="loading-state">
                <span class="material-symbols-outlined spin">progress_activity</span>
                <p>正在比对招标文件需求与企业资料...</p>
              </div>
              <div v-else>
                <span class="material-symbols-outlined">fact_check</span>
                <h4>尚未进行比对分析</h4>
                <p>点击左侧「开始比对分析」按钮，将招标文件中的各项需求与企业资料库进行智能匹配</p>
              </div>
            </div>

            <!-- 比对列表分页（summary 匹配率始终为全量值，分页仅展示层切分） -->
            <div class="comparison-pagination" v-if="comparisonData && filteredComparisonMatches.length > COMPARISON_PAGE_SIZE">
              <el-pagination
                v-model:current-page="comparisonPage"
                background
                layout="prev, pager, next"
                :total="filteredComparisonMatches.length"
                :page-size="COMPARISON_PAGE_SIZE"
              />
            </div>

            <!-- 批量操作 -->
            <div class="comparison-actions" v-if="comparisonData && comparisonData.summary.matched > 0">
              <el-button
                type="primary"
                :loading="batchGenerating"
                @click="handleBatchGenerateFromComparison"
              >
                <template #icon><span class="material-symbols-outlined">tips_and_updates</span></template>
                为已匹配需求批量生成响应 ({{ comparisonData.summary.matched }})
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab: Compliance Report -->
      <div v-show="activeTab === 'compliance'" class="tab-content">
        <RiskSummary
          :report="complianceReport"
          :loading="reportLoading"
          @recheck="handleRecheck"
          @export="exportDraft"
          @apply-fix="handleApplyFix"
        />
      </div>
    </div>

    <!-- Draft Panel (Drawer) -->
    <ResponseDraftPanel
      v-model="draftPanelVisible"
      :requirement="currentDraftReq"
      @saved="handleDraftSaved"
      @regenerate="handleRegenerateDraft"
      @status-change="handleDraftStatusChange"
    />

    <!-- Requirement Detail Dialog -->
    <el-dialog
      v-model="reqDetailVisible"
      :title="reqDetailTitle"
      width="640px"
      custom-class="req-detail-dialog"
    >
      <div v-if="currentReqDetail" class="req-detail-body">
        <!-- Meta tags -->
        <div class="req-detail-meta">
          <el-tag v-if="currentReqDetail.category" size="small">{{ getCategoryLabel(currentReqDetail.category) }}</el-tag>
          <el-tag v-if="currentReqDetail.priority" size="small" :type="getPriorityType(currentReqDetail.priority)">{{ currentReqDetail.priority }}</el-tag>
          <el-tag v-if="currentReqDetail.risk_level" size="small" :type="getRiskType(currentReqDetail.risk_level)">风险:{{ currentReqDetail.risk_level }}</el-tag>
          <el-tag v-if="currentReqDetail.response_status" size="small" type="info">响应:{{ currentReqDetail.response_status }}</el-tag>
          <el-tag v-else size="small" type="info">响应:未生成</el-tag>
        </div>

        <!-- Full content -->
        <div class="req-detail-section">
          <h4 class="req-detail-label">需求内容</h4>
          <p class="req-detail-content">{{ currentReqDetail.content }}</p>
        </div>

        <!-- Match sources -->
        <div class="req-detail-section" v-if="currentReqDetail.matchSources && currentReqDetail.matchSources.length">
          <h4 class="req-detail-label">匹配来源（{{ currentReqDetail.matchSources.length }}）</h4>
          <div v-for="(src, i) in currentReqDetail.matchSources" :key="i" class="req-detail-source">
            <span class="material-symbols-outlined text-primary">description</span>
            <span class="source-name">{{ src.filename || '未知来源' }}</span>
            <span class="source-score" v-if="src.score != null">相似度 {{ Number(src.score).toFixed(1) }}</span>
          </div>
        </div>
        <div class="req-detail-section" v-else>
          <h4 class="req-detail-label">匹配来源</h4>
          <p class="req-detail-muted">暂无匹配到的企业资料</p>
        </div>

        <!-- Source text (raw) -->
        <div class="req-detail-section" v-if="currentReqDetail.sourceText">
          <h4 class="req-detail-label">原始文本</h4>
          <p class="req-detail-source-text">{{ currentReqDetail.sourceText }}</p>
        </div>
      </div>
    </el-dialog>

    <!-- AI 项目助手（悬浮按钮 + 聊天抽屉） -->
    <AiChatPanel
      :project-id="projectId"
      @tools-executed="handleChatToolsExecuted"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { ElMessage, ElMessageBox } from 'element-plus'
import RequirementTable from '@/components/RequirementTable.vue'
import RiskSummary from '@/components/RiskSummary.vue'
import ResponseDraftPanel from '@/components/ResponseDraftPanel.vue'
import AiChatPanel from '@/components/AiChatPanel.vue'
import { parseServerDate } from '@/utils/date'
import {
  parseTenderDocument,
  batchDeleteRequirementsApi,
} from '@/api/projects'
import { runComplianceCheck as runComplianceCheckApi, getComplianceReport as getComplianceReportApi, remediateProject as remediateProjectApi, generateDraft as generateDraftApi, getDraft as getDraftApi, updateDraft as updateDraftApi, downloadReportMarkdown, downloadBidDocument, downloadBidPackage, analyzeMatches as analyzeMatchesApi, runMatchAnalysis as runMatchAnalysisApi, batchGenerateResponses as batchGenerateResponsesApi, getBatchStatus as getBatchStatusApi, pollMatchAnalysisTask } from '@/api/compliance'
import { parseResponse } from '@/utils/api'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

const activeTab = ref('tender')
const complianceReport = ref(null)
const reportLoading = ref(false)
const packaging = ref(false)  // 打包投递包 loading

// M7：轮询 AbortController——组件卸载时中止所有轮询，防止定时器泄漏
let matchPollCtrl = null
let batchPollCtrl = null
let remediatePollCtrl = null

const draftPanelVisible = ref(false)
const currentDraftReq = ref(null)
const reqDetailVisible = ref(false)
const currentReqDetail = ref(null)
const requirementTableRef = ref(null)  // 引用 RequirementTable 实例（暴露 getMatchInfo）
const reqDetailTitle = computed(() => currentReqDetail.value ? `需求详情 #${currentReqDetail.value.id}` : '需求详情')

const tenderDocs = computed(() => projectStore.tenderDocs)

const readiness = computed(() => projectStore.currentProject?.readiness || null)

// 标书导出门槛（与后端 can_submit 同口径）：无未处理高风险 且 综合就绪度 >= 95
// readiness 缺失（旧数据）时放行点击，由后端校验兜底
const canExportBid = computed(() => {
  const r = readiness.value
  if (!r) return true
  return !!r.can_submit
})
const exportBlockReason = computed(() => {
  const r = readiness.value
  if (!r || r.can_submit) return ''
  const parts = []
  if (r.high_risk_pending > 0) parts.push(`仍有 ${r.high_risk_pending} 个高风险项未处理`)
  if (r.overall < 95) parts.push(`响应就绪度 ${r.overall}%（需达到 95%）`)
  return parts.length ? `暂不可导出：${parts.join('，')}` : ''
})

const requirements = computed(() => {
  const reqs = projectStore.requirements
  return reqs.map(r => ({
    ...r,
    priority: (r.priority || '').toLowerCase(),
  }))
})

const technicalRequirements = computed(() => {
  return requirements.value
    .filter(r => r.category === '技术' || r.category === 'technical')
    .slice(0, 3)
    .map(r => ({
      content: r.content || r.description || '',
      tags: r.tags || []
    }))
})

const tabs = [
  { key: 'tender', label: '招标文件', icon: 'description' },
  { key: 'response', label: '响应清单', icon: 'list_alt' },
  { key: 'comparison', label: '比对分析', icon: 'fact_check' },
  { key: 'compliance', label: '合规报告', icon: 'verified_user' }
]

const projectId = computed(() => route.params.id)

// 比对分析相关状态
const comparing = ref(false)
const batchGenerating = ref(false)
// M9：比对结果派生自 projectStore（持久化），不再用 view-local ref，避免 tab 切换/重挂载导致历史结果丢失
const comparisonData = ref(null)

// 与 store 同步：autoLoadComparison 通过 setMatchAnalysis 写 store，
// 此 watch 触发 → comparisonData 更新（覆盖切到比对 tab 后的自动加载路径）。
// 同时支持 runComparisonSilent 直接赋值（改状态后静默刷新比对）。
watch(
  () => projectStore.currentProject?.matchAnalysis,
  (val) => { comparisonData.value = val },
  { immediate: true },
)
const comparisonFilter = ref('all')
// ---- 比对列表分页（前端 slice：匹配率 summary 始终全量，分页只切展示层）----
const COMPARISON_PAGE_SIZE = 20
const comparisonPage = ref(1)

const filteredComparisonMatches = computed(() => {
  if (!comparisonData.value?.matches) return []
  const matches = comparisonData.value.matches
  switch (comparisonFilter.value) {
    case 'matched': return matches.filter(m => m.has_match)
    case 'unmatched': return matches.filter(m => !m.has_match)
    default: return matches
  }
})

const pagedComparisonMatches = computed(() => {
  const start = (comparisonPage.value - 1) * COMPARISON_PAGE_SIZE
  return filteredComparisonMatches.value.slice(start, start + COMPARISON_PAGE_SIZE)
})

// 过滤切换 / 数据刷新 → 回第 1 页
function filterComparison(type) {
  comparisonFilter.value = type
  comparisonPage.value = 1
}

// 重新跑比对（comparisonData 整体替换）→ 回到第 1 页
watch(comparisonData, () => {
  comparisonPage.value = 1
})

function categoryCount(cat) {
  if (!comparisonData.value?.matches) return 0
  return comparisonData.value.matches.filter(m => (m.category || '').includes(cat)).length
}

function getCategoryTagType(cat) {
  const map = { '技术': 'primary', '商务': '', '资格': 'info', '评分': 'warning' }
  return map[cat] || ''
}

function getScoreTagType(score) {
  if (score >= 3) return 'success'
  if (score >= 1) return 'warning'
  return 'info'
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

// 轮询比对分析后台任务：启动返回 task_id → 每 2s 查 status → completed 后填充数据
// 委托给 compliance.js 共享轮询（与 RequirementTable 共用）；M7：传 signal 支持卸载中止
async function pollMatchAnalysis(taskId) {
  matchPollCtrl?.abort()  // 上一轮轮询若未结束先取消
  matchPollCtrl = new AbortController()
  return await pollMatchAnalysisTask(projectId.value, taskId, { signal: matchPollCtrl.signal })
}

async function runComparison() {
  if (!projectId.value) {
    ElMessage.warning('项目ID不存在')
    return
  }
  comparing.value = true
  try {
    // 用户主动触发 → 强制重新比对（POST 异步启动，立即返回 task_id，不阻塞 30s）
    const res = await runMatchAnalysisApi(projectId.value)
    const startData = parseResponse(res, null)
    if (!startData?.task_id) {
      ElMessage.error('比对分析任务启动失败')
      return
    }
    ElMessage.info('比对分析已启动，正在后台处理...')
    const finalData = await pollMatchAnalysis(startData.task_id)
    if (finalData) {
      projectStore.setMatchAnalysis(projectId.value, finalData)
    }
    if (finalData?.summary) {
      ElMessage.success(`比对完成: 匹配率 ${finalData.summary.match_rate}%`)
    }
  } catch (e) {
    ElMessage.error(e.message || '比对分析失败')
  } finally {
    comparing.value = false
  }
}

function formatLastAnalyzed(iso) {
  if (!iso) return ''
  try {
    // 后端 created_at 用 datetime.utcnow()，isoformat() 不带时区后缀。
    // 强制加 'Z' 让浏览器按 UTC 解析，再 .getHours() 等本地方法会自动转成本地时区。
    const d = new Date(typeof iso === 'string' && !/[Zz]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso + 'Z' : iso)
    const pad = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  } catch {
    return iso
  }
}

async function generateSingleResponse(requirementId) {
  try {
    const res = await generateDraftApi(requirementId)
    const data = parseResponse(res, {})
    if (data?.content) {
      ElMessage.success('响应生成成功')
      runComparison() // 重新比对以更新状态
    }
  } catch (e) {
    ElMessage.error(e.message || '生成响应失败')
  }
}

// 批量生成：改为「启动 → 每 2s 轮询 → 完成刷新」
// 解决前端 30s 超时硬墙：后端 batch-generate 立即返回 task_id，
// 后台线程跑 RAG + LLM；前端轮询 batch-status 查进度
async function handleBatchGenerateFromComparison() {
  if (!projectId.value) return
  try {
    await ElMessageBox.confirm(
      '确定要为已匹配的需求批量生成AI响应吗？此操作会调用AI服务，可能需要一些时间。',
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
    const startRes = await batchGenerateResponsesApi(projectId.value)
    const startData = parseResponse(startRes, {})

    // 没有待处理的已匹配需求
    if (!startData.task_id) {
      ElMessage.info(startData.message || '没有待处理的已匹配需求')
      return
    }

    const taskId = startData.task_id
    const total = startData.total || 0
    ElMessage.info(`批量生成任务已启动，共 ${total} 项，正在后台处理...`)

    // 2. 每 2s 轮询进度（M7：组件卸载时 abort，停止轮询）
    batchPollCtrl?.abort()
    batchPollCtrl = new AbortController()
    await new Promise((resolve, reject) => {
      pollTimer = setInterval(async () => {
        if (batchPollCtrl?.signal.aborted) {
          clearInterval(pollTimer); pollTimer = null
          reject(new Error('已取消'))
          return
        }
        try {
          const statusRes = await getBatchStatusApi(projectId.value, taskId)
          const status = parseResponse(statusRes, {})
          // 更新进度提示（可选：在 UI 上显示 processed/total）
          if (status.processed !== undefined && status.total) {
            // 可以在这里更新一个 reactive 进度变量给 UI 显示
          }
          // 终态：completed 或 failed
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
    }).then(status => status)

    // 3. 完成：刷新数据
    const statusRes = await getBatchStatusApi(projectId.value, taskId)
    const finalStatus = parseResponse(statusRes, {}) || {}
    // 解构兜底：字段缺失时不会显示 "undefined 项"
    const { succeeded = 0, skipped = 0, failed = 0 } = finalStatus
    ElMessage.success(`生成完成: 成功 ${succeeded} 项，跳过 ${skipped} 项${failed ? `，失败 ${failed} 项` : ''}`)
    await loadRequirements()
    runComparison()
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

async function loadRequirements() {
  const id = route.params.id
  if (id) {
    await projectStore.fetchRequirements(id)
  }
}

async function loadTenderDocs() {
  const id = route.params.id
  if (id) {
    await projectStore.fetchTenderDocs(id)
  }
}

watch(() => route.params.id, async (id) => {
  if (id) {
    await projectStore.fetchProject(id)
    await loadTenderDocs()
    await loadRequirements()
  }
}, { immediate: true })

onMounted(async () => {
  const id = route.params.id
  // M8：fetchProject/loadTenderDocs/loadRequirements 已由 watch(route.params.id, {immediate:true}) 首挂载执行，
  // 这里只补充 watch 不覆盖的合规报告预加载，避免重复请求与 loading 闪烁
  if (id) {
    await autoLoadComplianceReport()
  }
})

// M7：组件卸载时中止所有轮询，避免定时器与请求泄漏
onUnmounted(() => {
  matchPollCtrl?.abort()
  batchPollCtrl?.abort()
  remediatePollCtrl?.abort()
})

watch(activeTab, async (tab) => {
  if (!projectId.value) return
  if (tab === 'comparison') {
    // M9：每次切到比对分析 tab 主动拉一次（即使 store 有缓存），避免历史结果被永久锁在内存里看不到
    await autoLoadComparison()
  }
  if (tab === 'compliance') {
    // 每次进入合规 tab 强制刷新（修复"显示 11 但 DB 是 14"陈旧缓存问题）：
    // 合规 issue 是响应/合规重跑的结果，后端数据可能随时变化，前端不能盲目信任缓存
    complianceReport.value = null
    await autoLoadComplianceReport()
  }
})

async function autoLoadComparison() {
  if (!projectId.value) return
  comparing.value = true
  try {
    const res = await analyzeMatchesApi(projectId.value)
    const data = parseResponse(res, null)
    // 后端无历史时返回 {task_id, status:"running"} 启动异步比对 → 轮询等待
    if (data?.task_id && data?.status === 'running') {
      const finalData = await pollMatchAnalysis(data.task_id)
      if (finalData) {
        projectStore.setMatchAnalysis(projectId.value, finalData)
      }
    } else if (data && (data.summary || data.matches)) {
      // 有历史结果：写入 store（view 派生自 store，模板自动刷新）
      projectStore.setMatchAnalysis(projectId.value, data)
    } else {
      // 空响应（不应发生）：保留 null，让 UI 走"尚未进行"分支
      console.warn('[autoLoadComparison] 后端返回无 summary/matches 也无 task_id', data)
    }
  } catch (e) {
    // M9：失败必须可见（之前 console.error 静默吞，导致用户看到"查不到"却无任何反馈）
    console.error('自动加载比对分析失败:', e)
    ElMessage.error(`比对分析加载失败：${e?.message || '未知错误'}`)
  } finally {
    comparing.value = false
  }
}

async function autoLoadComplianceReport() {
  if (!projectId.value) return
  reportLoading.value = true
  try {
    const res = await getComplianceReportApi(projectId.value)
    complianceReport.value = parseResponse(res, {})
  } catch (e) {
    console.error('自动加载合规报告失败:', e)
  } finally {
    reportLoading.value = false
  }
}

function getStatusType(status) {
  switch (status) {
    case '准备中': return 'info'
    case '审核中': return 'warning'
    case '已完成': return 'success'
    default: return ''
  }
}

function getPriorityType(priority) {
  switch (priority) {
    case 'p0': return 'danger'
    case 'p1': return 'warning'
    default: return 'info'
  }
}

function getCategoryLabel(cat) {
  const map = { technical: '技术', business: '商务', qualification: '资格', scoring: '评分', 技术: '技术', 商务: '商务', 资格: '资格', 评分: '评分' }
  return map[cat] || cat || ''
}

function getRiskType(level) {
  const map = { 高: 'danger', 中: 'warning', 低: 'success' }
  return map[level] || 'info'
}

function getPriorityClass(priority) {
  switch (priority) {
    case 'p0': return 'priority-high'
    case 'p1': return 'priority-medium'
    default: return 'priority-normal'
  }
}

function getPriorityLabel(priority) {
  switch (priority) {
    case 'p0': return '高优先级'
    case 'p1': return '标准'
    default: return '一般'
  }
}

function formatDate(date) {
  if (!date) return '--'
  const d = parseServerDate(date)
  return d ? d.toLocaleDateString('zh-CN') : '--'
}

async function handleFileChange(uploadFile) {
  const id = route.params.id
  if (!id || !uploadFile.raw) return

  // L6：前端先校验 25MB 上限，超限直接拒绝（后端也会拦，但反馈更快）
  if (uploadFile.raw.size > 25 * 1024 * 1024) {
    ElMessage.error(`「${uploadFile.raw.name}」超过 25MB 上传上限`)
    return
  }

  const formData = new FormData()
  formData.append('file', uploadFile.raw)

  try {
    // L9：用上传接口返回的新文档 id 触发解析，避免多文件并发时都解析到列表第一项
    const created = await projectStore.uploadTender(id, formData)
    ElMessage.success('文件上传成功')
    await loadTenderDocs()

    const docId = created?.data?.id ?? projectStore.tenderDocs[0]?.id
    if (docId) {
      try {
        await parseTenderDocument(docId)
        await loadRequirements()
      } catch (parseErr) {
        console.error('解析失败:', parseErr)
      }
    }
  } catch {
    ElMessage.error('文件上传失败')
  }
}

// 招标文件解析成功态判定：兼容历史 parsed（旧 ParseAgent 状态词）与新 success（与路由/前端契约统一）
function isTenderDocSuccess(status) {
  return status === 'success' || status === 'parsed'
}

async function handleDeleteDoc(docId) {
  try {
    await projectStore.removeTenderDoc(docId)
  } catch (e) {
    // 仅主删除 API 失败才报「删除失败」；下面的刷新失败不应触发此提示
    ElMessage.error(e.message || '删除失败')
    return
  }
  ElMessage.success('招标文件已删除')
  // 删除成功 → 清理各 tab 本地缓存并刷新。刷新失败只 warn，不影响「已删除」的成功反馈。
  comparisonData.value = null
  complianceReport.value = null
  try {
    await Promise.all([loadRequirements(), loadProject()])
  } catch (e) {
    console.warn('[handleDeleteDoc] 删除后刷新 tab 失败（删除本身已成功）：', e)
  }
}

// 编辑需求：打开 AI 草案面板进行编辑（只加载已有草稿，不自动触发 AI 生成）
async function handleEditRequirement(req) {
  const reqId = typeof req === 'number' ? req : req.id
  const reqData = requirements.value.find(r => r.id === reqId)
  if (!reqData) return
  currentDraftReq.value = {
    id: reqData.id,
    title: reqData.content || reqData.title || '未命名需求',
    description: reqData.description || reqData.content || '',
    category: reqData.category || '',
    priority: reqData.priority || '',
    _loading: true,  // 先标记 loading：面板显示"加载中"而非空白，避免 watch 清空 draftContent 的空闪
  }
  draftPanelVisible.value = true
  try {
    // 只读加载已有草稿（GET，不调 LLM）；无草稿时面板显示空白可编辑
    const draftRes = await getDraftApi(reqId)
    const draftData = parseResponse(draftRes, {})
    currentDraftReq.value._draftContent = draftData?.content || draftData?.edited_content || ''
    currentDraftReq.value._sources = (draftData?.source_refs || []).map(s => {
      if (typeof s === 'string') return s
      // 保留完整对象（filename/content/score/source_ref），供面板溯源展示
      return s
    })
    currentDraftReq.value._status = draftData?.status || ''
  } catch {
    // 无草稿：清空，让用户手动编辑或点「重新生成」
    currentDraftReq.value._draftContent = ''
    currentDraftReq.value._sources = []
    currentDraftReq.value._status = ''
  } finally {
    // 必须清除 loading：触发面板 watch 渲染内容（无论成功失败）
    currentDraftReq.value._loading = false
  }
}

// 查看需求详情：完整内容 + 匹配来源 + 原始文本（区别于表格 2 行截断，展示增量信息）
function handleViewRequirement(req) {
  if (!req) return
  const id = typeof req === 'number' ? req : req.id
  // 内容来源：比对分析卡片传的是 match.content（已被后端 [:100] 截断用于卡片预览），
  // 详情弹窗需显示完整 → 按 id 从 projectStore 取已加载的完整 requirement.content
  // （loadRequirements 时已全量加载，store 里有完整数据）。
  const fullReq = projectStore.requirements?.find(r => r.id === id)
  const content = fullReq?.content || req.content || req.title || '未命名需求'

  // 匹配来源查找（按优先级）：
  // 1) req 自带（如比对分析 tab 传入的 match 对象）
  // 2) 父组件 comparisonData（独立加载的比对数据）
  // 3) 子组件 RequirementTable 内部 matchData（列表使用的同一份数据，保证一致性）
  let matchSources = req.matched_sources || []
  if (!matchSources.length && comparisonData.value?.matches) {
    const m = comparisonData.value.matches.find(x => x.requirement_id === id)
    if (m?.matched_sources?.length) {
      matchSources = m.matched_sources
    }
  }
  if (!matchSources.length && requirementTableRef.value?.getMatchInfo) {
    const m = requirementTableRef.value.getMatchInfo({ id })
    if (m?.matched_sources?.length) {
      matchSources = m.matched_sources
    }
  }

  // has_match 防御：未匹配时不显示匹配来源（避免与列表「未匹配」标签矛盾）
  let hasMatch = true
  if (req.has_match === false) hasMatch = false
  if (matchSources.length > 0) {
    // 仍尝试从子组件/父组件数据源拿 has_match
    if (comparisonData.value?.matches) {
      const m = comparisonData.value.matches.find(x => x.requirement_id === id)
      if (m) hasMatch = m.has_match !== false
    }
    if (hasMatch && requirementTableRef.value?.getMatchInfo) {
      const m = requirementTableRef.value.getMatchInfo({ id })
      if (m) hasMatch = m.has_match !== false
    }
  }
  if (!hasMatch) matchSources = []

  currentReqDetail.value = {
    id,
    content,
    category: req.category || '',
    priority: req.priority || '',
    risk_level: req.risk_level || '',
    response_status: req.response_status || null,
    matchSources,
    sourceText: req.source_text || '',
  }
  reqDetailVisible.value = true
}

// 批量删除需求
async function handleBatchDeleteRequirements(ids) {
  if (!ids?.length) return
  try {
    const res = await batchDeleteRequirementsApi(projectId.value, ids)
    const data = parseResponse(res, {})
    if (data?.deleted > 0) {
      ElMessage.success(`已删除 ${data.deleted} 项需求`)
    } else {
      ElMessage.warning('未找到可删除的需求项')
    }
    await loadRequirements()
  } catch (error) {
    ElMessage.error(error.message || '批量删除失败')
  }
}

async function handleGenerateDraft(reqId) {
  const req = requirements.value.find(r => r.id === reqId)
  if (!req) return
  currentDraftReq.value = {
    id: req.id,
    title: req.content || req.title || '未命名需求',
    description: req.description || req.content || '',
    category: req.category || '',
    priority: req.priority || '',
    _loading: true,  // 与 handleEditRequirement 一致：加载中显示骨架，避免空白闪烁
  }
  draftPanelVisible.value = true
  try {
    const genRes = await generateDraftApi(reqId)
    const draftData = parseResponse(genRes, {})
    currentDraftReq.value._draftContent = draftData?.content || ''
    currentDraftReq.value._sources = (draftData?.source_refs || []).map(s => {
      if (typeof s === 'string') return s
      // 保留完整对象（filename/content/score/source_ref），供面板溯源展示
      return s
    })
    currentDraftReq.value._status = draftData?.status || ''
  } catch {
    currentDraftReq.value._draftContent = ''
    currentDraftReq.value._sources = []
  } finally {
    currentDraftReq.value._loading = false
  }
}

// L12：面板自管保存请求与 loading（saving 由面板 try/finally 复位），
// 这里只做保存成功后的副作用：刷新需求列表（status/内容最新态）
async function handleDraftSaved() {
  try {
    await loadRequirements()
  } catch {
    // 刷新失败不打断用户（数据下次进入/操作时自动补齐）
  }
}

async function handleRegenerateDraft() {
  if (!currentDraftReq.value) return
  const reqId = currentDraftReq.value.id
  // 与 handleGenerateDraft/handleEditRequirement 同一套 loading 生命周期：
  // _loading=true → 面板显示骨架；finally _loading=false → 面板刷新内容
  currentDraftReq.value._loading = true
  try {
    // force=true：真正触发后端重新生成（绕开「已存在草稿」拦截），而非直接返回旧稿
    const genRes = await generateDraftApi(reqId, true)
    // 防串台：请求期间用户可能已切换需求/关闭面板，丢弃过期结果，不写错对象
    if (!currentDraftReq.value || currentDraftReq.value.id !== reqId) return
    const draftData = parseResponse(genRes, {})
    currentDraftReq.value._draftContent = draftData?.content || ''
    currentDraftReq.value._sources = (draftData?.source_refs || []).map(s => {
      if (typeof s === 'string') return s
      // 保留完整对象（filename/content/score/source_ref），供面板溯源展示
      return s
    })
    // 同步状态：重新生成后后端会回写 pending_review/needs_manual，
    // 实现「已驳回 → 重新生成 → 自动回到待审核」的审核流闭环
    currentDraftReq.value._status = draftData?.status || ''
  } catch (e) {
    if (!currentDraftReq.value || currentDraftReq.value.id !== reqId) return
    ElMessage.error(e?.message || '重新生成失败')
  } finally {
    if (currentDraftReq.value && currentDraftReq.value.id === reqId) {
      currentDraftReq.value._loading = false
    }
  }
}

async function handleDraftStatusChange(payload) {
  if (!currentDraftReq.value) return
  // L5：面板切状态时携带编辑内容 {status, content}；兼容旧调用（纯字符串）
  const status = typeof payload === 'string' ? payload : payload?.status
  const content = typeof payload === 'string' ? undefined : payload?.content
  try {
    const body = { status }
    if (typeof content === 'string' && content.trim()) {
      body.edited_content = content  // 未保存的编辑内容随状态一起提交，防止丢失
    }
    await updateDraftApi(currentDraftReq.value.id, body)
    // 立即更新本地状态，确保面板即时反映变更
    currentDraftReq.value._status = status
    ElMessage.success('状态已更新')
    await loadRequirements()
    // 仅在比对标签页时刷新比对数据（响应列表已通过 loadRequirements 更新）
    if (activeTab.value === 'comparison') {
      await runComparisonSilent()
    }
  } catch {
    ElMessage.error('状态更新失败')
  }
}

async function runComparisonSilent() {
  if (!projectId.value) return
  try {
    const res = await analyzeMatchesApi(projectId.value)
    const data = parseResponse(res, null)
    // 无历史时后端返回 task_id 异步启动 → 轮询
    if (data?.task_id && data?.status === 'running') {
      const finalData = await pollMatchAnalysis(data.task_id)
      comparisonData.value = finalData
    } else {
      comparisonData.value = data
    }
  } catch (e) {
    console.error('静默比对更新失败:', e)
  }
}

async function handleRecheck() {
  const id = route.params.id
  if (!id) return
  reportLoading.value = true
  try {
    await runComplianceCheckApi(id)
    const res = await getComplianceReportApi(id)
    complianceReport.value = parseResponse(res, {})
    ElMessage.success('合规核查完成')
  } catch {
    ElMessage.error('合规核查失败')
  } finally {
    reportLoading.value = false
  }
}

// 项目级补救（原每条风险卡片的"应用建议"已提升为 RiskSummary 头部"生成补救计划"按钮，
// 不再接收单条 item——作用于本项目全部未处理风险）
async function handleApplyFix() {
  const id = route.params.id
  if (!id) return
  // 真实落地：调 /remediate 生成补救计划（按 rule_code 映射为可执行动作），
  // 缺资料类引导上传、响应缺失类触发重新生成（异步轮询）、其余人工处理
  try {
    const res = await remediateProjectApi(id)
    const data = parseResponse(res, {})
    const plan = data?.plan || []
    const total = plan.length
    if (total === 0) {
      ElMessage.info(data?.message || '暂无未处理风险需要补救')
      return
    }
    const uploadCount = plan.filter(p => p.action === 'upload_materials').length
    const regenCount = plan.filter(p => p.action === 'regenerate').length
    const manualCount = total - uploadCount - regenCount

    // 缺口 B：有 regenerate → 后台异步生成，前端轮询 batch-status，完成后刷新
    if (regenCount > 0 && data.regenerate_task_id) {
      // L4：明确是"项目级补救计划"，避免用户误以为只处理当前这一条风险
      ElMessage.success(`已为项目全部未处理风险生成补救计划：${uploadCount} 项需上传企业资料、${regenCount} 项已触发重新生成、${manualCount} 项待人工处理，正在后台生成...`)
      remediatePollCtrl?.abort()
      remediatePollCtrl = new AbortController()
      await pollRemediateBatch(id, data.regenerate_task_id, { signal: remediatePollCtrl.signal })
      // P0-1：响应重新生成后自动重跑合规核查，重建风险清单。
      // 若不重跑，compliance_issues 旧记录残留，风险项不会消失（用户会误以为"应用建议"没生效）
      try {
        await runComplianceCheckApi(id)
      } catch (e) {
        console.warn('补救后自动重跑合规核查失败（响应已更新，可手动点击重新核查）:', e)
      }
      await Promise.all([loadRequirements(), autoLoadComplianceReport()])
      ElMessage.success(`重新生成完成：${regenCount} 项已更新，风险报告已刷新`)
    } else {
      let msg = `已为项目全部未处理风险生成补救计划：${total} 项`
      if (uploadCount) msg += `，${uploadCount} 项需上传企业资料`
      if (manualCount) msg += `，${manualCount} 项待人工处理`
      ElMessage.success(msg)
    }

    // 缺口 A：有 upload_materials → 弹窗引导前往企业资料库上传
    if (uploadCount > 0) {
      try {
        await ElMessageBox.confirm(
          `有 ${uploadCount} 项风险需要补充企业资料（资质证书、类似案例、技术方案等）。\n是否前往「企业资料库」上传？上传后回来重新核查即可。`,
          '需要补充企业资料',
          { confirmButtonText: '前往上传', cancelButtonText: '稍后处理', type: 'warning' }
        )
        router.push('/company-materials')
      } catch { /* 用户取消，不跳转 */ }
    }
  } catch (e) {
    ElMessage.error(e?.message || '生成补救计划失败')
  }
}

// AI 助手执行了工具（重新核查/补救等）→ 刷新各 tab 数据
async function handleChatToolsExecuted() {
  try {
    await Promise.all([
      loadRequirements(),
      autoLoadComplianceReport(),
      autoLoadComparison().catch(() => {}),
    ])
  } catch { /* 刷新失败不打断用户聊天 */ }
}

// 轮询补救计划触发的批量重新生成任务（复用 batch-status 轻量接口）
// M7：支持 AbortSignal——组件卸载时中止
function pollRemediateBatch(projectId, taskId, { intervalMs = 3000, timeoutMs = 600000, signal = null } = {}) {
  return new Promise((resolve, reject) => {
    let timeoutHandle = null
    const cleanup = () => { clearInterval(timer); if (timeoutHandle) clearTimeout(timeoutHandle) }
    const timer = setInterval(async () => {
      if (signal?.aborted) {
        cleanup()
        reject(new Error('已取消'))
        return
      }
      try {
        const res = await getBatchStatusApi(projectId, taskId)
        const status = parseResponse(res, {})
        if (status?.status === 'completed') {
          cleanup()
          resolve(status)
        } else if (status?.status === 'failed') {
          cleanup()
          reject(new Error(status?.error || '重新生成任务失败'))
        }
      } catch (e) {
        cleanup()
        reject(e)
      }
    }, intervalMs)
    timeoutHandle = setTimeout(() => { cleanup(); reject(new Error('重新生成任务超时')) }, timeoutMs)
  })
}

async function exportDraft() {
  const id = route.params.id
  if (!id) return
  try {
    const blob = await downloadReportMarkdown(id)
    const url = window.URL.createObjectURL(new Blob([blob]))
    const a = document.createElement('a')
    a.href = url
    a.download = `compliance-report-${id}.md`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
    ElMessage.success('报告已导出')
  } catch {
    ElMessage.error('导出失败')
  }
}

// 导出投标响应文件（合并全部需求响应；format: markdown | pdf）
async function exportBidDocument(format = 'markdown') {
  const id = route.params.id
  if (!id) return
  if (exportBlockReason.value) {
    ElMessage.warning(exportBlockReason.value)
    return
  }
  try {
    const blob = await downloadBidDocument(id, format)
    const ext = format === 'pdf' ? 'pdf' : 'md'
    const url = window.URL.createObjectURL(new Blob([blob]))
    const a = document.createElement('a')
    a.href = url
    a.download = `bid-document-${id}.${ext}`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
    ElMessage.success('标书已导出')
  } catch (e) {
    ElMessage.error(e?.message || '标书导出失败')
  }
}

// 打包投递包
async function exportBidPackage() {
  const id = route.params.id
  if (!id) return
  if (exportBlockReason.value) {
    ElMessage.warning(exportBlockReason.value)
    return
  }
  packaging.value = true
  try {
    const blob = await downloadBidPackage(id)
    const url = window.URL.createObjectURL(new Blob([blob]))
    const a = document.createElement('a')
    a.href = url
    a.download = `bid-package-${id}.zip`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
    ElMessage.success('投递包已生成')
  } catch (e) {
    ElMessage.error(e?.message || '打包失败')
  } finally {
    packaging.value = false
  }
}

</script>

<style scoped>
.project-detail {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.project-header {
  background: var(--surface-container-lowest);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.header-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.header-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-title-row h1 {
  font-size: 24px;
  font-weight: 700;
  color: var(--on-surface);
  margin: 0;
}

.status-tag {
  font-weight: 600;
  border-radius: 9999px;
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--on-surface-variant);
  margin: 0;
}

.header-meta .material-symbols-outlined {
  font-size: 16px;
}

.header-right-info {
  text-align: right;
}

.deadline-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--on-surface-variant);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}

.deadline-value {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  font-size: 18px;
  font-weight: 600;
  color: var(--error);
}

.header-bottom {
  display: flex;
  flex-wrap: wrap;          /* 窄屏按钮组换到下一行，进度条永远完整可见 */
  gap: 16px 20px;
  align-items: center;
  padding-top: 20px;
  border-top: 1px solid var(--border-subtle);
}

.progress-section {
  flex: 1 1 320px;          /* 进度区占满剩余空间，最小 320px */
  min-width: 0;             /* 允许 flex 收缩，进度条不被按钮挤压 */
}

.progress-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
}

.progress-pct {
  font-weight: 700;
  color: var(--primary);
  font-size: 18px;          /* 加大让百分比更醒目 */
  font-variant-numeric: tabular-nums;  /* 等宽数字避免抖动 */
}

.readiness-breakdown {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  font-size: 12px;
  flex-wrap: wrap;
}

.breakdown-tag {
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--surface-container-highest);
  color: var(--on-surface-variant);
}

.risk-tag {
  padding: 2px 8px;
  border-radius: 4px;
  background: #fef2f2;
  color: #dc2626;
  font-weight: 600;
}

.header-actions {
  display: flex;
  gap: 8px;                  /* 紧凑间距，避免按钮挤进度条 */
  flex-shrink: 0;            /* 按钮组不被进度区压缩 */
}

.export-btn {
  /* 覆盖 Element Plus plain 默认亮蓝(#409EFF 白底对比度仅~3:1，低于 AA 4.5:1)，
     改用项目主题深蓝 #005bbf + 淡蓝底 → 文字清晰可读 */
  border: 1px solid #005bbf;
  color: #005bbf !important;
  background: rgba(0, 91, 191, 0.07) !important;
  font-weight: 600;
}
.export-btn:hover {
  background: rgba(0, 91, 191, 0.14) !important;
}

.submit-btn {
  font-weight: 600;
}

/* Tab container */
.tab-container {
  background: var(--surface-container-lowest);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  overflow: hidden;
}

.tab-headers {
  display: flex;
  border-bottom: 1px solid var(--border-subtle);
  padding: 0 24px;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 24px;
  border: none;
  background: none;
  font-size: 15px;
  font-weight: 600;
  color: var(--on-surface-variant);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.tab-btn:hover {
  color: var(--primary);
}

.tab-btn.active {
  color: var(--primary);
  border-bottom-color: var(--primary);
}

.tab-content {
  padding: 24px;
}

/* Tender layout */
.tender-layout {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 24px;
}

.upload-panel,
.analysis-panel {
  background: var(--surface-container-lowest);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 24px;
}

.upload-panel h3,
.analysis-header h3 {
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.upload-zone {
  margin-bottom: 16px;
}

.upload-dragger :deep(.el-upload-dragger) {
  border-radius: 12px;
  padding: 32px 16px;
  border-color: var(--border-subtle);
  border-style: dashed;
  background: var(--surface-container-low);
  transition: all 0.2s;
}

.upload-dragger :deep(.el-upload-dragger:hover) {
  border-color: var(--primary);
  background: var(--surface-container-low);
}

.upload-icon {
  font-size: 48px;
  color: var(--on-surface-variant);
}

.upload-title {
  font-size: 14px;
  font-weight: 600;
  margin: 8px 0 4px;
  color: var(--on-surface);
}

.upload-hint {
  font-size: 12px;
  color: var(--on-surface-variant);
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.file-item {
  padding: 12px;
  border-radius: 8px;
}

.file-item.uploading {
  background: var(--surface-gray);
  border: 1px solid var(--border-subtle);
}

.file-item:not(.uploading) {
  background: var(--surface-container-lowest);
  border: 1px solid var(--border-subtle);
}

.file-uploading {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.file-uploading .material-symbols-outlined {
  font-size: 18px;
}

.file-progress {
  margin-left: auto;
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
}

.file-done {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-done .material-symbols-outlined {
  font-size: 18px;
}

.file-name {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  color: var(--on-surface);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-more {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
}

.file-more:hover {
  background: var(--surface-container);
}

.empty-files {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
  color: var(--on-surface-variant);
}

.empty-files .material-symbols-outlined {
  font-size: 32px;
  color: var(--outline-variant);
}

.empty-files p {
  font-size: 13px;
}

/* Analysis panel */
.analysis-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: -24px -24px 24px -24px;
  padding: 16px 24px;
  background: var(--surface-container-low);
  border-radius: 12px 12px 0 0;
}

.req-count {
  font-weight: 600;
}

.analysis-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.analysis-section h4 {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--on-surface-variant);
  margin-bottom: 12px;
}

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.info-item {
  padding: 16px;
  background: var(--surface-gray);
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
}

.info-label {
  display: block;
  font-size: 12px;
  color: var(--on-surface-variant);
  margin-bottom: 4px;
}

.info-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--on-surface);
}

.req-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.req-card {
  padding: 16px;
  border-radius: 8px;
}

.ai-accent {
  background: rgba(26, 115, 232, 0.05);
  border-left: 4px solid var(--primary);
}

.priority-tag {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}

.priority-high {
  background: var(--error);
  color: white;
}

.priority-medium {
  background: var(--warning-amber);
  color: #1a1a1a;
}

.priority-normal {
  background: var(--outline);
  color: white;
}

.tech-card {
  padding: 16px;
  background: var(--surface-gray);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
}

.tech-content {
  font-size: 14px;
  color: var(--on-surface);
  line-height: 1.6;
  margin-bottom: 12px;
}

.tech-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tech-tag {
  font-size: 12px;
  padding: 4px 10px;
  background: rgba(43, 91, 181, 0.1);
  color: var(--primary);
  border-radius: 6px;
}

.req-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.req-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--primary);
}

.req-desc {
  font-size: 14px;
  color: var(--on-surface);
  line-height: 1.6;
  margin-bottom: 8px;
}

.req-source {
  font-size: 12px;
  color: var(--outline);
  font-style: italic;
  margin: 0;
}

.empty-req {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
  background: var(--surface-gray);
  border-radius: 8px;
  border: 1px dashed var(--outline-variant);
  color: var(--on-surface-variant);
}

.empty-req .material-symbols-outlined {
  font-size: 32px;
  color: var(--outline-variant);
}

.empty-req p {
  font-size: 13px;
  text-align: center;
}

/* Empty state for response tab */
.empty-state-card {
  background: var(--surface-container-lowest);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 48px 32px;
  text-align: center;
}

.empty-icon {
  font-size: 72px;
  color: var(--outline-variant);
  margin-bottom: 16px;
}

.empty-state-card h3 {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 8px;
}

.empty-state-card p {
  font-size: 16px;
  color: var(--on-surface-variant);
  max-width: 480px;
  margin: 0 auto 24px;
}

/* Comparison Layout */
.comparison-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 24px;
}

.comparison-sidebar {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.comparison-summary,
.comparison-stats {
  background: var(--surface-container-lowest);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 20px;
}

.comparison-summary h3,
.comparison-stats h4 {
  font-size: 14px;
  font-weight: 700;
  color: var(--on-surface);
  margin: 0 0 16px 0;
}

.summary-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}

.summary-card {
  padding: 16px;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: center;
}

.summary-card .summary-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
}

.summary-card .summary-label {
  font-size: 12px;
  color: var(--on-surface-variant);
}

.summary-card.total {
  background: rgba(26, 115, 232, 0.1);
}
.summary-card.total .summary-value {
  color: var(--primary);
}

.summary-card.matched {
  background: rgba(52, 168, 83, 0.1);
}
.summary-card.matched .summary-value {
  color: #34a853;
}

.summary-card.unmatched {
  background: rgba(234, 67, 53, 0.1);
}
.summary-card.unmatched .summary-value {
  color: #ea4335;
}

.summary-card.rate {
  background: rgba(251, 188, 4, 0.1);
  grid-column: 1 / -1;
}
.summary-card.rate .summary-value {
  color: #f9ab00;
}

.summary-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 12px;
  color: var(--on-surface-variant);
  font-size: 13px;
  margin-bottom: 16px;
}

.summary-empty .material-symbols-outlined {
  font-size: 40px;
  color: var(--outline-variant);
}

.summary-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  font-size: 12px;
  color: var(--on-surface-variant);
}

.summary-meta .material-symbols-outlined {
  font-size: 16px !important;
  color: var(--outline);
}

.comparison-btn {
  width: 100%;
  margin-top: 12px;
}

.comparison-stats .stats-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.stats-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: var(--surface-gray);
  border-radius: 8px;
  font-size: 13px;
}

.stats-item strong {
  color: var(--primary);
}

/* Comparison detail */
.comparison-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--surface-container-lowest);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 16px 20px;
}

.detail-header h3 {
  font-size: 16px;
  font-weight: 700;
  margin: 0;
}

.detail-actions {
  display: flex;
  gap: 8px;
}

.detail-actions .el-button.active {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.comparison-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.comparison-item {
  background: var(--surface-container-lowest);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 20px;
  transition: all 0.2s;
}

.comparison-item.matched {
  border-left: 4px solid #34a853;
}

.comparison-item.unmatched {
  border-left: 4px solid #ea4335;
  background: rgba(234, 67, 53, 0.03);
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.item-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.item-id {
  font-weight: 700;
  color: var(--on-surface-variant);
  font-size: 13px;
}

.priority-indicator {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}

.priority-indicator.p0 {
  background: var(--error);
  color: white;
}
.priority-indicator.p1 {
  background: #fbbc04;
  color: #1a1a1a;
}
.priority-indicator.p2 {
  background: var(--outline);
  color: white;
}

.item-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
}

.content-row {
  display: flex;
  gap: 8px;
  font-size: 14px;
  line-height: 1.6;
}

.content-label {
  font-weight: 600;
  color: var(--on-surface-variant);
  flex-shrink: 0;
}

.content-text {
  color: var(--on-surface);
  /* 比对分析卡片预览截断：避免长需求 content 撑高卡片布局，完整内容在「查看详情」弹窗 */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

.source-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
}

.source-item {
  padding: 12px;
  background: rgba(52, 168, 83, 0.05);
  border: 1px solid rgba(52, 168, 83, 0.2);
  border-radius: 8px;
}

.source-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.source-filename {
  font-weight: 600;
  font-size: 13px;
  color: var(--on-surface);
}

.source-preview {
  margin: 0;
  font-size: 13px;
  color: var(--on-surface-variant);
  line-height: 1.5;
}

.no-match-hint {
  color: #ea4335;
  font-size: 13px;
  font-style: italic;
}

.item-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
}

.comparison-empty {
  background: var(--surface-container-lowest);
  border: 1px dashed var(--outline-variant);
  border-radius: 12px;
  padding: 48px 32px;
  text-align: center;
  color: var(--on-surface-variant);
}

.comparison-empty .material-symbols-outlined {
  font-size: 64px;
  color: var(--outline-variant);
  margin-bottom: 16px;
}

.comparison-empty h4 {
  font-size: 18px;
  font-weight: 700;
  margin: 0 0 8px 0;
  color: var(--on-surface);
}

.comparison-empty p {
  font-size: 14px;
  max-width: 400px;
  margin: 0 auto;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.loading-state .spin {
  animation: spin 1.5s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.comparison-actions {
  display: flex;
  justify-content: center;
  padding: 16px;
  background: var(--surface-container-low);
  border-radius: 12px;
  border: 1px solid var(--border-subtle);
}

/* 比对列表分页：居中，与列表间距 */
.comparison-pagination {
  display: flex;
  justify-content: center;
  margin-top: 14px;
}

@media (max-width: 1024px) {
  .tender-layout {
    grid-template-columns: 1fr;
  }
  .comparison-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .header-top {
    flex-direction: column;
    gap: 16px;
  }

  .header-bottom {
    grid-template-columns: 1fr;
  }

  .header-right-info {
    text-align: left;
  }

  .deadline-value {
    justify-content: flex-start;
  }

  .summary-cards {
    grid-template-columns: 1fr 1fr;
  }

  .item-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}

/* Requirement detail dialog */
.req-detail-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.req-detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.req-detail-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.req-detail-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--outline);
  margin: 0;
}

.req-detail-content {
  font-size: 14px;
  color: var(--on-surface);
  line-height: 1.7;
  margin: 0;
  max-height: 240px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--surface-container-low);
  border-radius: 8px;
  padding: 12px;
}

.req-detail-source {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--on-surface-variant);
  padding: 6px 10px;
  background: var(--surface-container-low);
  border-radius: 8px;
}

.req-detail-source .source-name {
  flex: 1;
  word-break: break-all;
}

.req-detail-source .source-score {
  color: var(--primary);
  font-weight: 600;
  white-space: nowrap;
}

.req-detail-muted {
  font-size: 13px;
  color: var(--outline);
  margin: 0;
}

.req-detail-source-text {
  font-size: 12px;
  color: var(--on-surface-variant);
  line-height: 1.6;
  margin: 0;
  max-height: 160px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--surface-container-low);
  border-radius: 8px;
  padding: 10px;
}

.text-primary { color: var(--primary); }
</style>
