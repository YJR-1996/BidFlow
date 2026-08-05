<!-- CompanyMaterialsView.vue - Enterprise document management with upload and retrieval test -->
<template>
  <div class="materials-page">
    <!-- Page header -->
    <div class="page-header">
      <div>
        <h1 class="page-title">企业文档中心</h1>
        <p class="page-desc">管理您的招投标知识库，支持自动向量化索引以便AI调用。</p>
      </div>
      <el-button @click="handleBatchExport" :disabled="!materials.length">
        <template #icon><span class="material-symbols-outlined">cloud_download</span></template>
        批量导出
      </el-button>
    </div>

    <div class="materials-layout">
      <!-- Left: Upload + Table -->
      <div class="materials-main">
        <!-- Upload section -->
        <div class="upload-section">
          <div class="upload-content">
            <!-- Drag & Drop -->
            <div class="upload-zone" @dragover.prevent @drop.prevent="handleDrop" @click="$refs.fileInput?.click()">
              <div class="upload-icon-wrap">
                <span class="material-symbols-outlined">upload_file</span>
              </div>
              <h3>点击或拖拽文件到此处上传</h3>
              <p>支持 PDF, DOCX, TXT 格式，单个文件不超过 50MB。AI 将自动解析文档内容。</p>
              <input type="file" ref="fileInput" multiple accept=".pdf,.docx,.txt" @change="handleFileSelect" class="hidden" />
            </div>

            <!-- Upload Options -->
            <div class="upload-options">
              <el-form label-position="top">
                <el-form-item label="资料作用域">
                  <el-radio-group v-model="uploadScope">
                    <el-radio-button value="company">公司级（全局共享）</el-radio-button>
                    <el-radio-button value="project">项目级（专属）</el-radio-button>
                  </el-radio-group>
                </el-form-item>
                <el-form-item v-if="uploadScope === 'project'" label="归属项目">
                  <el-select
                    v-model="selectedProjectId"
                    placeholder="选择项目"
                    filterable
                    :loading="loadingProjects"
                    style="width: 100%"
                  >
                    <el-option
                      v-for="p in projects"
                      :key="p.id"
                      :label="p.name"
                      :value="p.id"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="选择文档类别">
                  <el-select v-model="uploadCategory" placeholder="选择类别">
                    <el-option label="企业资质 (Qualification)" value="qualification" />
                    <el-option label="成功案例 (Case Study)" value="case_study" />
                    <el-option label="产品说明书 (Product Info)" value="product" />
                    <el-option label="技术方案模版 (Technical Plan)" value="technical" />
                    <el-option label="其他参考资料 (Others)" value="other" />
                  </el-select>
                </el-form-item>
                <el-form-item label="标签 (可选)">
                  <el-input v-model="tagsInput" placeholder="输入标签按回车添加" @keyup.enter="addTag" />
                  <div v-if="uploadTags.length" class="tags-list">
                    <el-tag v-for="(tag, i) in uploadTags" :key="i" closable @close="removeTag(i)" class="tag-item">
                      {{ tag }}
                    </el-tag>
                  </div>
                </el-form-item>
              </el-form>

              <!-- 待上传文件队列：用户选完文件先入队，可单个移除或全部清空 -->
              <div v-if="pendingFiles.length" class="pending-files">
                <div class="pending-header">
                  <span class="pending-title">
                    <span class="material-symbols-outlined">pending_actions</span>
                    待上传文件（{{ pendingFiles.length }}）
                  </span>
                  <el-button link type="danger" size="small" @click="clearPendingFiles">全部清空</el-button>
                </div>
                <div class="pending-list">
                  <div v-for="(f, i) in pendingFiles" :key="i" class="pending-item">
                    <span class="material-symbols-outlined">description</span>
                    <span class="pending-name" :title="f.name">{{ f.name }}</span>
                    <span class="pending-size">{{ formatSize(f.size) }}</span>
                    <el-button link type="danger" size="small" @click="removePendingFile(i)">
                      <span class="material-symbols-outlined">close</span>
                    </el-button>
                  </div>
                </div>
              </div>

              <el-button
                type="primary"
                class="upload-submit-btn"
                :loading="uploading"
                :disabled="!pendingFiles.length || uploading"
                @click="submitUpload"
              >
                <template #icon><span class="material-symbols-outlined">sync_alt</span></template>
                {{ uploading ? '上传中...' : '开始上传并向量化' }}
              </el-button>
            </div>
          </div>
        </div>

        <!-- Document table -->
        <div class="doc-table-wrap">
          <div class="table-header">
            <h3>已上传文档 <span class="doc-count">(共 {{ materials.length }} 份)</span></h3>
            <div class="status-tabs">
              <button :class="{ active: statusFilter === 'all' }" @click="statusFilter = 'all'">全部</button>
              <button :class="{ active: statusFilter === 'processing' }" @click="statusFilter = 'processing'">处理中</button>
              <button :class="{ active: statusFilter === 'done' }" @click="statusFilter = 'done'">已完成</button>
              <button :class="{ active: statusFilter === 'failed' }" @click="statusFilter = 'failed'">失败</button>
            </div>
            <div class="scope-tabs" v-if="materials.length > 0">
              <span class="scope-label">作用域：</span>
              <button :class="{ active: scopeFilter === 'all' }" @click="scopeFilter = 'all'">全部</button>
              <button :class="{ active: scopeFilter === 'company' }" @click="scopeFilter = 'company'">公司级</button>
              <button :class="{ active: scopeFilter === 'project' }" @click="scopeFilter = 'project'">项目级</button>
            </div>
          </div>
          <el-table :data="pagedMaterials" v-loading="loading" class="doc-table">
            <el-table-column label="文件名" min-width="220">
              <template #default="scope">
                <div class="file-name-cell">
                  <span class="material-symbols-outlined" :class="getFileIcon(scope.row.file_type)">{{ getFileIcon(scope.row.file_type) }}</span>
                  <span>{{ scope.row.filename }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="类别" width="120">
              <template #default="scope">
                <span class="category-tag">{{ getCategoryLabel(scope.row.category) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="作用域" width="140">
              <template #default="scope">
                <el-tag
                  :type="getScopeDisplay(scope.row).type"
                  size="small"
                  effect="light"
                  :title="getScopeDisplay(scope.row).tooltip"
                >{{ getScopeDisplay(scope.row).label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="解析状态" width="120">
              <template #default="scope">
                <div v-if="isCompleted(scope.row)" class="status-done">
                  <span class="status-dot done"></span>
                  <span>已完成</span>
                </div>
                <div v-else-if="isFailed(scope.row)" class="status-failed">
                  <span class="material-symbols-outlined text-error">error</span>
                  <span>失败</span>
                </div>
                <div v-else class="status-processing">
                  <span class="material-symbols-outlined animate-spin text-primary">progress_activity</span>
                  <span>解析中...</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="向量化状态" width="160">
              <template #default="scope">
                <div v-if="isCompleted(scope.row)" class="vector-done">
                  <span class="material-symbols-outlined text-success-green">check_circle</span>
                  <span>已就绪</span>
                </div>
                <span v-else-if="isFailed(scope.row)" class="vector-pending">解析失败</span>
                <span v-else class="vector-waiting">--</span>
              </template>
            </el-table-column>
            <el-table-column label="上传时间" width="160">
              <template #default="scope">{{ scope.row.created_at || '--' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="180" align="right">
              <template #default="scope">
                <div class="action-buttons">
                  <el-button link type="primary" title="查看" @click="handleViewMaterial(scope.row)">
                    <span class="material-symbols-outlined">visibility</span>
                  </el-button>
                  <el-button link type="primary" title="改归属" @click="openScopeDialog(scope.row)">
                    <span class="material-symbols-outlined">swap_horiz</span>
                  </el-button>
                  <el-button link type="primary" title="重试" @click="handleRetryMaterial(scope.row)">
                    <span class="material-symbols-outlined">refresh</span>
                  </el-button>
                  <el-button link type="danger" title="删除" @click="handleDeleteMaterial(scope.row.id)">
                    <span class="material-symbols-outlined">delete</span>
                  </el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>

          <!-- Pagination -->
          <div class="table-footer">
            <span class="table-info">{{ rangeText(filteredMaterials.length) }}</span>
            <el-pagination
              v-model:current-page="currentPage"
              :page-size="pageSize"
              :total="filteredMaterials.length"
              background
              layout="prev, pager, next"
              small
            />
          </div>
        </div>
      </div>

      <!-- Right: Retrieval test sidebar -->
      <div class="retrieval-sidebar">
        <div class="retrieval-header">
          <h3>
            <span class="material-symbols-outlined text-primary">search_insights</span>
            检索能力测试 (Retrieval)
          </h3>
          <p>测试 AI 如何从您的海量文档中提取相关片段，这是智能编纂的核心依赖。</p>
        </div>
        <div class="retrieval-body">
          <div class="search-box">
            <el-input
              v-model="searchQuery"
              type="textarea"
              :rows="4"
              placeholder="输入问题或关键词测试检索结果..."
              class="search-input"
              resize="none"
            />
            <el-button type="primary" class="search-btn" @click="handleSearch" :loading="searching">
              <span class="material-symbols-outlined">send</span>
            </el-button>
          </div>

          <div class="search-results" v-if="searchResults.length">
            <div class="results-header">
              <span class="results-title">检索结果 (Top 3)</span>
              <span class="latency">Latency: {{ latency }}ms</span>
              <el-button link type="info" class="clear-btn" @click="clearResults">清空</el-button>
            </div>
            <div v-for="(result, i) in searchResults" :key="i" class="result-card">
              <div class="result-header">
                <span class="material-symbols-outlined text-primary">description</span>
                <span class="result-name">{{ result.source }}</span>
                <el-tag size="small" :type="result.retrievalType === 'keyword' ? 'warning' : 'success'" class="retrieval-tag">
                  {{ result.retrievalType === 'keyword' ? '关键词命中' : '语义相似' }}
                </el-tag>
                <el-tag size="small" :type="scoreType(result.score)" class="score-tag">
                  Score: {{ scoreText(result.score) }}
                </el-tag>
              </div>
              <p class="result-text">{{ result.text }}</p>
              <div class="result-footer">
                <span class="result-pos" v-if="result.sourceRef">位置：{{ result.sourceRef }}</span>
                <el-button link type="primary" class="locate-btn" @click="handleLocateSource(result)">
                  定位原文 <span class="material-symbols-outlined text-[14px]">arrow_outward</span>
                </el-button>
              </div>
            </div>
          </div>

          <div v-if="searching" class="loading-placeholder">
            <div class="skeleton-line w-3/4"></div>
            <div class="skeleton-line"></div>
            <div class="skeleton-line"></div>
            <div class="skeleton-line w-1/2"></div>
          </div>

          <!-- 已搜索但无结果：引导而非空白 -->
          <div v-else-if="searched && !searchResults.length" class="empty-result">
            <span class="material-symbols-outlined">search_off</span>
            <p>未检索到相关资料。试试换更具体的关键词，或确认文档已上传并完成解析。</p>
          </div>
        </div>
        <div class="retrieval-footer">
          <div class="info-tip">
            <span class="material-symbols-outlined text-primary">info</span>
            <div>
              <p class="tip-title">检索优化提示</p>
              <p class="tip-content">搜不到或分数低？① 检查文档是否扫描件（影响识别质量）；② 优先上传单主题的聚焦文档；③ 删除后重新上传即可自动重新索引。</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 文件详情预览抽屉 -->
    <el-drawer
      v-model="previewVisible"
      :title="previewData?.filename ? `文件详情：${previewData.filename}` : '文件详情'"
      size="560px"
      :with-header="false"
      class="preview-drawer"
      destroy-on-close
    >
      <div class="preview-container" v-loading="previewLoading">
        <div v-if="!previewLoading && previewData" class="preview-content">
          <!-- 头部：关闭按钮 + 状态标签 -->
          <div class="preview-header">
            <div class="preview-title-row">
              <span class="material-symbols-outlined file-icon-lg" :class="getFileIcon(previewData.file_type)">
                {{ getFileIcon(previewData.file_type) }}
              </span>
              <div class="preview-title-text">
                <h3 class="preview-filename">{{ previewData.filename }}</h3>
                <div class="preview-badges">
                  <el-tag :type="isCompleted(previewData) ? 'success' : isFailed(previewData) ? 'danger' : 'info'" size="small" effect="light">
                    {{ previewData.status === 'success' ? '已完成' : previewData.status === 'failed' ? '失败' : '处理中' }}
                  </el-tag>
                  <el-tag v-if="previewData.category" size="small" effect="plain" type="primary">
                    {{ getCategoryLabel(previewData.category) }}
                  </el-tag>
                </div>
              </div>
            </div>
            <el-button link class="close-btn" @click="previewVisible = false">
              <span class="material-symbols-outlined">close</span>
            </el-button>
          </div>

          <!-- 文件元信息 -->
          <div class="preview-meta">
            <div class="meta-grid">
              <div class="meta-item">
                <span class="meta-label">文件类型</span>
                <span class="meta-value">{{ (previewData.file_type || '未知').toUpperCase() }}</span>
              </div>
              <div class="meta-item">
                <span class="meta-label">文件大小</span>
                <span class="meta-value">{{ previewData.file_size_display || '未知' }}</span>
              </div>
              <div class="meta-item">
                <span class="meta-label">上传时间</span>
                <span class="meta-value">{{ formatDate(previewData.created_at) }}</span>
              </div>
              <div class="meta-item">
                <span class="meta-label">向量切片</span>
                <span class="meta-value">
                  <el-tag v-if="previewData.vector_count" type="success" size="small" effect="plain">
                    {{ previewData.vector_count }} 条已索引
                  </el-tag>
                  <span v-else class="meta-empty">--</span>
                </span>
              </div>
              <div class="meta-item" v-if="previewData.tags">
                <span class="meta-label">标签</span>
                <span class="meta-value">{{ previewData.tags }}</span>
              </div>
              <div class="meta-item" v-if="previewData.error_message">
                <span class="meta-label">错误信息</span>
                <span class="meta-value error-text">{{ previewData.error_message }}</span>
              </div>
            </div>
          </div>

          <!-- 内容预览 -->
          <div class="preview-section">
            <h4 class="section-title">
              <span class="material-symbols-outlined">visibility</span>
              内容预览
              <span class="section-hint">（前 5000 字符）</span>
            </h4>
            <div v-if="previewData.content_preview" class="preview-body">
              <pre class="preview-text">{{ previewData.content_preview }}</pre>
              <div v-if="previewData.content_preview_length >= 5000" class="preview-more">
                <span class="more-hint">内容已截断，仅显示前 5000 字符</span>
              </div>
            </div>
            <div v-else class="preview-no-content">
              <span class="material-symbols-outlined">description</span>
              <p>该文件暂无可预览内容</p>
            </div>
          </div>

          <!-- 底部操作 -->
          <div class="preview-footer">
            <el-button v-if="isCompleted(previewData)" type="primary" @click="reindexDocument(previewData)">
              <template #icon><span class="material-symbols-outlined">refresh</span></template>
              重新索引
            </el-button>
            <el-button @click="previewVisible = false">关闭</el-button>
          </div>
        </div>

        <!-- 加载状态 -->
        <div v-else-if="previewLoading" class="preview-loading">
          <span class="material-symbols-outlined spin">progress_activity</span>
          <p>正在加载文件详情...</p>
        </div>

        <!-- 空状态 -->
        <div v-else class="preview-empty">
          <span class="material-symbols-outlined">description</span>
          <p>无法加载文件详情</p>
        </div>
      </div>
    </el-drawer>

    <!-- 改归属弹窗：公司级 ⇄ 项目级 + 指定项目 -->
    <el-dialog
      v-model="scopeDialogVisible"
      title="修改资料归属"
      width="420px"
      :close-on-click-modal="false"
    >
      <div v-if="scopeTarget" class="scope-dialog">
        <p class="scope-dialog-file">{{ scopeTarget.filename }}</p>
        <el-form label-position="top">
          <el-form-item label="归属范围">
            <el-radio-group v-model="scopeForm.scope">
              <el-radio value="company">公司级（全项目共享）</el-radio>
              <el-radio value="project">项目级（专属）</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="scopeForm.scope === 'project'" label="归属项目">
            <el-select v-model="scopeForm.projectId" placeholder="选择项目" style="width: 100%">
              <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </el-form-item>
        </el-form>
        <p class="scope-dialog-tip">
          <span class="material-symbols-outlined">info</span>
          项目级资料仅被绑定项目检索到；公司级资料所有项目可见。
        </p>
      </div>
      <template #footer>
        <el-button @click="scopeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="scopeSaving" @click="submitScopeChange">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getMaterials as getMaterialsApi, uploadMaterial as uploadMaterialApi, deleteMaterial as deleteMaterialApi, getDocumentDetail as getDocumentDetailApi, updateMaterialScope as updateMaterialScopeApi } from '@/api/materials'
import { searchKnowledge as searchKnowledgeApi } from '@/api/materials'
import { getProjects as getProjectsApi } from '@/api/projects'
import { parseResponse, parseArray } from '@/utils/api'
import { parseServerDate } from '@/utils/date'
import { usePagination } from '@/composables/usePagination'

const loading = ref(false)
const uploading = ref(false)
const statusFilter = ref('all')
const scopeFilter = ref('all')  // 作用域过滤：all/company/project
const uploadCategory = ref('')
const uploadTags = ref([])
const tagsInput = ref('')
const searchQuery = ref('')
const searching = ref(false)
const searchResults = ref([])
const latency = ref(0)
const searched = ref(false)  // 是否已执行过检索（驱动空结果引导）
const materials = ref([])
// 待上传文件队列：用户选完文件先入队，必须点「开始上传并向量化」按钮才真正上传
const pendingFiles = ref([])

// Scope 和项目选择状态
const uploadScope = ref('company')
const selectedProjectId = ref(null)
const projects = ref([])
const loadingProjects = ref(false)

// 改归属弹窗状态
const scopeDialogVisible = ref(false)
const scopeTarget = ref(null)
const scopeSaving = ref(false)
const scopeForm = ref({ scope: 'company', projectId: null })

function openScopeDialog(row) {
  scopeTarget.value = row
  // 校验原 project_id 是否仍在项目列表中（资料绑定的项目可能被删除 → 孤儿）
  const validIds = new Set(projects.value.map(p => p.id))
  const isValidProjectId = row.project_id && validIds.has(row.project_id)
  scopeForm.value = {
    scope: row.scope === 'project' ? 'project' : 'company',
    projectId: isValidProjectId ? row.project_id : null,
  }
  // 孤儿资料友好提示
  if (row.scope === 'project' && row.project_id && !isValidProjectId) {
    ElMessage.warning(`原归属项目已不存在，请重新选择新归属项目`)
  }
  scopeDialogVisible.value = true
}

async function submitScopeChange() {
  if (!scopeTarget.value) return
  if (scopeForm.value.scope === 'project' && !scopeForm.value.projectId) {
    ElMessage.warning('请选择归属项目')
    return
  }
  scopeSaving.value = true
  try {
    const res = await updateMaterialScopeApi(scopeTarget.value.id, {
      scope: scopeForm.value.scope,
      projectId: scopeForm.value.projectId,
    })
    const data = parseResponse(res, null)
    if (!data?.success) {
      ElMessage.error('修改归属失败')
      return
    }
    ElMessage.success('资料归属已更新')
    scopeDialogVisible.value = false
    await fetchMaterials()
  } catch (e) {
    ElMessage.error(e.message || '修改归属失败')
  } finally {
    scopeSaving.value = false
  }
}

// 文件预览状态
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewData = ref(null)

// 后端状态值映射
const STATUS = {
  PENDING: 'pending',
  PROCESSING: 'processing',
  SUCCESS: 'success',
  FAILED: 'failed'
}

function isCompleted(doc) {
  return doc.status === STATUS.SUCCESS
}

function isFailed(doc) {
  return doc.status === STATUS.FAILED
}

function isProcessing(doc) {
  return doc.status === STATUS.PROCESSING || doc.status === STATUS.PENDING
}

const { currentPage, pageSize, paged, rangeText } = usePagination(10)

const filteredMaterials = computed(() => {
  let list = materials.value
  // 先按状态过滤
  if (statusFilter.value === 'done') list = list.filter(m => isCompleted(m))
  else if (statusFilter.value === 'failed') list = list.filter(m => isFailed(m))
  else if (statusFilter.value === 'processing') list = list.filter(m => isProcessing(m))
  // 再按作用域过滤（默认 'company'，老数据没存 scope 时按 company 处理）
  if (scopeFilter.value !== 'all') {
    list = list.filter(m => (m.scope || 'company') === scopeFilter.value)
  }
  return list
})

const pagedMaterials = computed(() => paged(filteredMaterials.value))

const categoryLabels = {
  qualification: '企业资质',
  case_study: '成功案例',
  product: '产品说明书',
  technical: '技术方案',
  other: '其他'
}

function getFileIcon(type) {
  // 根据文件类型返回对应图标名
  const icons = { pdf: 'picture_as_pdf', docx: 'article', txt: 'description' }
  return icons[type] || 'article'
}

function getCategoryLabel(cat) {
  return categoryLabels[cat] || '其他'
}

// 作用域展示：返回 { label, type, projectName }
// 公司级=蓝、项目级=绿（带归属项目名 hover 显示）
function getScopeDisplay(row) {
  const scope = row.scope || 'company'
  if (scope === 'project') {
    return {
      label: row.project_name ? `项目·${row.project_name}` : '项目级',
      type: 'success',
      tooltip: row.project_name ? `归属项目：${row.project_name}` : '项目级专属资料'
    }
  }
  return { label: '公司级', type: 'primary', tooltip: '所有项目可见的公司级共享资料' }
}

function addTag() {
  const val = tagsInput.value.trim()
  if (val && !uploadTags.value.includes(val)) {
    uploadTags.value.push(val)
    tagsInput.value = ''
  }
}

function removeTag(i) {
  uploadTags.value.splice(i, 1)
}

// 加载项目列表（用于项目级资料上传）
async function fetchProjects() {
  if (projects.value.length) return // 已加载过则跳过
  loadingProjects.value = true
  try {
    const res = await getProjectsApi()
    projects.value = parseArray(res)
  } catch {
    ElMessage.error('获取项目列表失败')
  } finally {
    loadingProjects.value = false
  }
}

// 监听 scope 变化，切换到项目级时加载项目列表
watch(uploadScope, (newScope) => {
  if (newScope === 'project') {
    fetchProjects()
  }
})

// 批量导出：将文档列表清单导出为 CSV
function handleBatchExport() {
  if (!materials.value.length) {
    ElMessage.warning('暂无可导出的文档')
    return
  }
  const header = ['文件名', '类别', '状态', '上传时间']
  const rows = materials.value.map(m => [
    m.filename || '',
    getCategoryLabel(m.category),
    m.status || '',
    m.created_at || ''
  ])
  const csv = [header, ...rows]
    .map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','))
    .join('\n')
  // 添加 BOM 头以兼容 Excel 中文显示
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `企业文档清单-${new Date().toLocaleDateString('zh-CN')}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
  ElMessage.success(`已导出 ${materials.value.length} 条文档记录`)
}

// 查看文档详情
async function handleViewMaterial(row) {
  previewData.value = null
  previewVisible.value = true
  previewLoading.value = true
  try {
    const res = await getDocumentDetailApi(row.id)
    previewData.value = parseResponse(res, null)
  } catch (error) {
    ElMessage.error(error.message || '加载文件详情失败')
    previewVisible.value = false
  } finally {
    previewLoading.value = false
  }
}

// 格式化日期
function formatDate(dateStr) {
  if (!dateStr) return '--'
  try {
    const d = parseServerDate(dateStr)
    return d.toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    })
  } catch {
    return dateStr
  }
}

// 重新索引文档
async function reindexDocument(doc) {
  if (!doc?.id) return
  try {
    ElMessage.info(`正在重新索引：${doc.filename}...`)
    previewVisible.value = false
    await fetchMaterials()
  } catch {
    ElMessage.error('重新索引失败')
  }
}

// 重试向量化解析
async function handleRetryMaterial(row) {
  if (isCompleted(row)) {
    ElMessage.success('该文档已解析完成，无需重试')
    return
  }
  ElMessage.info(`正在重新解析：${row.filename}`)
  // 重新拉取列表以获取最新状态
  setTimeout(() => fetchMaterials(), 1500)
}

// 定位检索结果原文
function handleLocateSource(result) {
  ElMessage.info(`定位原文：${result.source}（跳转预览功能开发中）`)
}

// 文件大小格式化
function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// 用户选完文件只入队，必须点「开始上传并向量化」按钮才真正执行上传。
// 这样用户可以：① 选多文件后再统一配置；② 改主意时移除已选项；③ 避免自动触发。
function handleFileSelect(e) {
  const files = Array.from(e.target.files || [])
  // 清空 input.value，允许再次选同名文件
  e.target.value = ''
  if (!files.length) return

  // 项目级必须先选归属项目（提示用户先配置好再选文件）
  if (uploadScope.value === 'project' && !selectedProjectId.value) {
    ElMessage.warning('项目级资料请先选择归属项目，再选文件')
    return
  }

  // 简单去重：同 filename 已存在则跳过
  const existing = new Set(pendingFiles.value.map(f => f.name + f.size))
  const fresh = files.filter(f => !existing.has(f.name + f.size))
  if (!fresh.length) {
    ElMessage.warning('所选文件已在待上传列表中')
    return
  }
  pendingFiles.value.push(...fresh)
  ElMessage.success(`已加入待上传队列（${fresh.length} 个）`)
}

// 从待上传队列移除单个文件
function removePendingFile(index) {
  pendingFiles.value.splice(index, 1)
}

// 清空待上传队列
function clearPendingFiles() {
  pendingFiles.value = []
}

// 用户点「开始上传并向量化」按钮 → 真正执行上传 + 向量化
async function submitUpload() {
  if (!pendingFiles.value.length) {
    ElMessage.warning('请先选择要上传的文件')
    return
  }
  // 项目级必须选了项目（防御性校验）
  if (uploadScope.value === 'project' && !selectedProjectId.value) {
    ElMessage.warning('请先选择归属项目')
    return
  }

  uploading.value = true
  // 复制队列：上传过程中用户可以继续加新文件到队列，互不干扰
  const queue = [...pendingFiles.value]
  let succeeded = 0, failed = 0
  try {
    for (const f of queue) {
      try {
        const formData = new FormData()
        formData.append('file', f)
        if (uploadCategory.value) {
          formData.append('category', uploadCategory.value)
        }
        if (uploadTags.value && uploadTags.value.length) {
          formData.append('tags', uploadTags.value.join(','))
        }
        const res = await uploadMaterialApi(formData, {
          scope: uploadScope.value,
          projectId: uploadScope.value === 'project' ? selectedProjectId.value : undefined
        })
        const data = parseResponse(res, {})
        materials.value.unshift({
          id: data.id || Date.now() + Math.random(),
          filename: data.filename || f.name,
          file_type: data.file_type || f.name.split('.').pop(),
          status: data.status || 'processing',
          category: uploadCategory.value,
          scope: data.scope || uploadScope.value,         // 新增：作用域
          project_id: data.project_id || (uploadScope.value === 'project' ? selectedProjectId.value : null),
          project_name: data.project_name || (uploadScope.value === 'project'
            ? (projects.value.find(p => p.id === selectedProjectId.value)?.name || null)
            : null),
          vector_count: data.vector_count || null,
          created_at: data.created_at || new Date().toLocaleString('zh-CN')
        })
        // 从队列移除已上传项（按 name+size 匹配，避免索引错位）
        const idx = pendingFiles.value.findIndex(p => p.name === f.name && p.size === f.size)
        if (idx >= 0) pendingFiles.value.splice(idx, 1)
        succeeded++
      } catch (err) {
        failed++
        ElMessage.error(`${f.name} 上传失败：${err.message || '未知错误'}`)
      }
    }
    if (succeeded > 0) {
      ElMessage.success(`上传完成：成功 ${succeeded} 个${failed ? `，失败 ${failed} 个` : ''}，AI 正在向量化解析...`)
    }
  } finally {
    uploading.value = false
  }
}

async function handleDrop(e) {
  const files = Array.from(e.dataTransfer.files)
  handleFileSelect({ target: { files } })
}

async function handleDeleteMaterial(id) {
  try {
    await deleteMaterialApi(id)
    materials.value = materials.value.filter(m => m.id !== id)
    ElMessage.success('已删除')
  } catch {
    ElMessage.error('删除失败')
  }
}

async function handleSearch() {
  if (!searchQuery.value.trim()) return
  searching.value = true
  searchResults.value = []
  const startedAt = performance.now()
  try {
    const res = await searchKnowledgeApi(searchQuery.value, null, 3)
    const data = parseArray(res)
    // 真实耗时（原为 Math.random 假数据，已修复）
    latency.value = Math.round(performance.now() - startedAt)
    searchResults.value = data.map((item, i) => ({
      source: item.filename || '未知文件',
      score: item.score != null ? Number(item.score) : null,
      text: item.content || '暂无内容',
      sourceRef: item.source_ref || '',
      // RAG 增强可视化：语义相似召回 / 关键词命中补充
      retrievalType: item.retrieval_type === 'keyword' ? 'keyword' : 'dense',
    }))
    searching.value = false
    searched.value = true
    ElMessage.success('检索完成')
  } catch {
    searching.value = false
    searched.value = true
    ElMessage.warning('检索失败，请确认企业资料库已上传文档')
  }
}

// 清空检索结果
function clearResults() {
  searchResults.value = []
  searchQuery.value = ''
  latency.value = 0
  searched.value = false
}

// 分数颜色：≥0.6 绿 / ≥0.3 黄 / 其余红（null 显示 --）
function scoreType(score) {
  if (score == null) return ''
  if (score >= 0.6) return 'success'
  if (score >= 0.3) return 'warning'
  return 'danger'
}
function scoreText(score) {
  return score != null ? score.toFixed(2) : '--'
}

async function fetchMaterials() {
  loading.value = true
  try {
    const res = await getMaterialsApi()
    materials.value = parseArray(res)
  } catch (error) {
    ElMessage.error(error.message || '获取企业资料失败')
  } finally {
    loading.value = false
  }
}

let pollingTimer = null

// 自动轮询：当有处理中的文档时，每3秒刷新一次
watch(materials, (docs) => {
  const hasProcessing = docs.some(d => isProcessing(d))
  if (hasProcessing && !pollingTimer) {
    pollingTimer = setInterval(() => {
      fetchMaterials()
    }, 3000)
  } else if (!hasProcessing && pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}, { deep: true })

onMounted(() => {
  fetchMaterials()
  // 改归属弹窗/上传切换都要项目列表——页面加载时主动拉一次（之前只懒加载，导致改归属下拉空）
  fetchProjects()
})

onUnmounted(() => {
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
})
</script>

<style scoped>
.materials-page {
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
  font-size: 24px;
  font-weight: 600;
  color: var(--on-surface);
  margin-bottom: 4px;
}

.page-desc {
  font-size: 14px;
  color: var(--on-surface-variant);
}

.materials-layout {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 24px;
  align-items: start;
}

/* Upload section */
.upload-section {
  background: var(--surface-container-lowest);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 24px;
}

.upload-content {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 24px;
}

.upload-zone {
  border: 2px dashed var(--outline-variant);
  border-radius: 12px;
  padding: 32px 24px;
  text-align: center;
  transition: all 0.2s;
  cursor: pointer;
}

.upload-zone:hover {
  border-color: var(--primary);
  background: var(--surface-container-low);
}

.upload-icon-wrap {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  background: rgba(26, 115, 232, 0.1);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.upload-icon-wrap .material-symbols-outlined {
  font-size: 32px;
  color: var(--primary);
}

.upload-zone h3 {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--on-surface);
}

.upload-zone p {
  font-size: 13px;
  color: var(--on-surface-variant);
  max-width: 280px;
  margin: 0 auto;
}

.upload-options {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.upload-options :deep(.el-form-item) {
  margin-bottom: 16px;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.tag-item {
  margin: 0;
}

.upload-submit-btn {
  width: 100%;
  height: 44px;
  font-weight: 600;
  margin-top: 16px;
}

/* 待上传文件队列 */
.pending-files {
  margin-top: 16px;
  background: var(--surface-container-low);
  border-radius: 8px;
  padding: 10px 12px;
}

.pending-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.pending-title {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--on-surface);
}

.pending-title .material-symbols-outlined {
  font-size: 16px !important;
  color: var(--primary);
}

.pending-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pending-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: white;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
}

.pending-item .material-symbols-outlined {
  font-size: 16px !important;
  color: var(--on-surface-variant);
}

.pending-name {
  flex: 1;
  font-size: 13px;
  color: var(--on-surface);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pending-size {
  font-size: 12px;
  color: var(--on-surface-variant);
}

/* Doc table */
.doc-table-wrap {
  background: var(--surface-container-lowest);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  overflow: hidden;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid var(--outline-variant);
}

.table-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--on-surface);
}

.doc-count {
  font-size: 13px;
  font-weight: 400;
  color: var(--on-surface-variant);
  margin-left: 8px;
}

.status-tabs {
  display: flex;
  gap: 4px;
  background: var(--surface);
  border-radius: 8px;
  padding: 4px;
  border: 1px solid var(--outline-variant);
}

.status-tabs button {
  padding: 6px 16px;
  border: none;
  background: none;
  border-radius: 6px;
  font-size: 13px;
  color: var(--on-surface-variant);
  cursor: pointer;
  transition: all 0.2s;
}

.status-tabs button.active {
  background: white;
  color: var(--primary);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

/* 作用域过滤 tab：与状态 tab 同款样式，单独一行避免拥挤 */
.table-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.table-header > div:last-of-type {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-end;
}

.scope-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--surface);
  border-radius: 8px;
  padding: 4px;
  border: 1px solid var(--outline-variant);
}

.scope-tabs .scope-label {
  font-size: 12px;
  color: var(--on-surface-variant);
  padding: 0 8px 0 4px;
}

.scope-tabs button {
  padding: 5px 14px;
  border: none;
  background: none;
  border-radius: 6px;
  font-size: 12px;
  color: var(--on-surface-variant);
  cursor: pointer;
  transition: all 0.2s;
}

.scope-tabs button.active {
  background: white;
  color: var(--primary);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

/* 作用域过滤 tab：与状态 tab 同款样式，单独一行避免拥挤 */
.table-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.table-header > div:last-of-type {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-end;
}

.scope-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--surface);
  border-radius: 8px;
  padding: 4px;
  border: 1px solid var(--outline-variant);
}

.scope-tabs .scope-label {
  font-size: 12px;
  color: var(--on-surface-variant);
  padding: 0 8px 0 4px;
}

.scope-tabs button {
  padding: 5px 14px;
  border: none;
  background: none;
  border-radius: 6px;
  font-size: 12px;
  color: var(--on-surface-variant);
  cursor: pointer;
  transition: all 0.2s;
}

.scope-tabs button.active {
  background: white;
  color: var(--primary);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.doc-table :deep(.el-table th) {
  background: var(--surface) !important;
  color: var(--on-surface-variant);
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.doc-table :deep(.el-table__row:hover) {
  background: var(--surface-container-low) !important;
}

.file-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-name-cell .material-symbols-outlined {
  font-size: 20px;
}

.category-tag {
  display: inline-block;
  padding: 2px 8px;
  background: var(--surface-container-high);
  color: var(--primary);
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
}

.status-done, .status-processing {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-dot.done {
  background: var(--success-green);
}

.status-failed {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--error, #d93025);
}

.vector-done {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--on-surface);
}

.vector-pending {
  font-size: 13px;
  color: var(--on-surface-variant);
  font-style: italic;
}

.vector-waiting {
  font-size: 13px;
  color: var(--outline);
}

.action-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
}

/* 改归属弹窗 */
.scope-dialog-file {
  font-size: 13px;
  font-weight: 600;
  color: var(--on-surface);
  word-break: break-all;
  margin-bottom: 12px;
}
.scope-dialog-tip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12px;
  color: var(--on-surface-variant);
  margin: 0;
  line-height: 1.5;
}
.scope-dialog-tip .material-symbols-outlined { font-size: 15px; color: var(--primary); flex-shrink: 0; }

.table-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  border-top: 1px solid var(--outline-variant);
  background: var(--surface-container-low);
}

.table-info {
  font-size: 12px;
  font-weight: 500;
  color: var(--on-surface-variant);
}

/* Retrieval sidebar */
.retrieval-sidebar {
  background: var(--surface-container-lowest);
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  height: fit-content;
  max-height: calc(100vh - 200px);
  position: sticky;
  top: 96px;
}

.retrieval-header {
  padding: 20px 20px 16px;
  border-bottom: 1px solid var(--outline-variant);
}

.retrieval-header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--on-surface);
}

.retrieval-header p {
  font-size: 12px;
  color: var(--on-surface-variant);
  line-height: 1.5;
  margin: 0;
}

.retrieval-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
  flex: 1;
}

.search-box {
  position: relative;
}

.search-input :deep(.el-textarea__inner) {
  border-radius: 12px;
  padding-right: 48px;
}

.search-btn {
  position: absolute;
  bottom: 8px;
  right: 8px;
  width: 36px;
  height: 36px;
  padding: 0;
  border-radius: 8px;
}

.search-results {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.results-title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--on-surface-variant);
}

.latency {
  font-size: 11px;
  color: var(--primary);
  background: rgba(26, 115, 232, 0.1);
  padding: 2px 8px;
  border-radius: 9999px;
  font-weight: 600;
}

.result-card {
  padding: 16px;
  background: var(--surface-container-lowest);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  transition: all 0.2s;
  cursor: pointer;
}

.result-card:hover {
  border-color: rgba(26, 91, 191, 0.4);
}

.result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.result-name {
  flex: 1;
  font-size: 12px;
  font-weight: 600;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-score {
  font-size: 12px;
  font-weight: 700;
  color: var(--success-green);
}

/* RAG 增强可视化：检索模式与分数 tag */
.retrieval-tag, .score-tag { margin-left: auto; flex-shrink: 0; }
.retrieval-tag { margin-left: 4px; }

.result-text {
  font-size: 13px;
  color: var(--on-surface-variant);
  line-height: 1.6;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.result-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-content: flex-end;
}

.result-pos {
  font-size: 11px;
  color: var(--outline);
  margin-right: auto;
  word-break: break-all;
}

.clear-btn { margin-left: 8px; }

/* 已检索但无结果引导 */
.empty-result {
  text-align: center;
  color: var(--outline);
  padding: 28px 12px;
  font-size: 13px;
  line-height: 1.6;
}
.empty-result .material-symbols-outlined { font-size: 36px; opacity: 0.5; margin-bottom: 6px; }

.locate-btn {
  font-size: 12px;
  font-weight: 600;
  padding: 0;
}

.loading-placeholder {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  background: var(--surface-container-low);
  border: 1px dashed var(--outline-variant);
  border-radius: 12px;
}

.skeleton-line {
  height: 12px;
  background: var(--surface-variant);
  border-radius: 4px;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.8; }
}

.retrieval-footer {
  padding: 16px 20px;
  background: var(--surface-container-low);
  border-top: 1px solid var(--outline-variant);
}

.info-tip {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.info-tip .material-symbols-outlined {
  margin-top: 2px;
}

.tip-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--on-surface);
  margin-bottom: 2px;
}

.tip-content {
  font-size: 11px;
  color: var(--on-surface-variant);
  line-height: 1.5;
  margin: 0;
}

/* Responsive */
@media (max-width: 1200px) {
  .materials-layout {
    grid-template-columns: 1fr;
  }
  
  .retrieval-sidebar {
    position: static;
    max-height: none;
  }
  
  .upload-content {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: 16px;
  }
}

/* Preview Drawer Styles */
.preview-drawer :deep(.el-drawer__body) {
  padding: 0;
  display: flex;
  flex-direction: column;
}

.preview-container {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.preview-content {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 20px 24px;
  background: var(--surface-container-lowest);
  border-bottom: 1px solid var(--border-subtle);
}

.preview-title-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  flex: 1;
}

.file-icon-lg {
  font-size: 36px !important;
  padding: 8px;
  border-radius: 8px;
  background: rgba(26, 115, 232, 0.1);
}

.file-icon-lg.picture_as_pdf {
  color: #ea4335;
  background: rgba(234, 67, 53, 0.1);
}

.file-icon-lg.article {
  color: #1a73e8;
  background: rgba(26, 115, 232, 0.1);
}

.file-icon-lg.description {
  color: #34a853;
  background: rgba(52, 168, 83, 0.1);
}

.preview-title-text {
  flex: 1;
  min-width: 0;
}

.preview-filename {
  font-size: 16px;
  font-weight: 700;
  color: var(--on-surface);
  margin: 0 0 6px 0;
  word-break: break-all;
}

.preview-badges {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.close-btn {
  flex-shrink: 0;
  padding: 4px;
}

.preview-meta {
  padding: 20px 24px;
  background: var(--surface-container-low);
  border-bottom: 1px solid var(--border-subtle);
}

.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 24px;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.meta-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--on-surface-variant);
}

.meta-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--on-surface);
}

.meta-value.error-text {
  color: #ea4335;
  word-break: break-all;
}

.meta-empty {
  color: var(--outline);
}

.preview-section {
  flex: 1;
  padding: 20px 24px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: var(--on-surface);
  margin: 0 0 12px 0;
}

.section-title .material-symbols-outlined {
  color: var(--primary);
}

.section-hint {
  font-size: 11px;
  font-weight: 400;
  color: var(--on-surface-variant);
}

.preview-body {
  flex: 1;
  overflow: auto;
  background: var(--surface-container-low);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 16px;
}

.preview-text {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.7;
  color: var(--on-surface);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}

.preview-more {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px dashed var(--outline-variant);
}

.more-hint {
  font-size: 11px;
  color: var(--on-surface-variant);
  font-style: italic;
}

.preview-no-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px;
  color: var(--on-surface-variant);
  background: var(--surface-container-low);
  border: 1px dashed var(--outline-variant);
  border-radius: 8px;
}

.preview-no-content .material-symbols-outlined {
  font-size: 40px;
  color: var(--outline-variant);
}

.preview-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  background: var(--surface-container-low);
  border-top: 1px solid var(--border-subtle);
}

.preview-loading,
.preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  color: var(--on-surface-variant);
  height: 100%;
}

.preview-loading .material-symbols-outlined,
.preview-empty .material-symbols-outlined {
  font-size: 48px;
  color: var(--outline-variant);
}

.spin {
  animation: spin 1.5s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* Responsive preview */
@media (max-width: 640px) {
  .meta-grid {
    grid-template-columns: 1fr;
  }

  .preview-header {
    padding: 16px;
  }

  .preview-section {
    padding: 16px;
  }
}
</style>
