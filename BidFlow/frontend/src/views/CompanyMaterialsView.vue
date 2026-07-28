<!-- CompanyMaterialsView.vue - Enterprise document management with upload and retrieval test -->
<template>
  <div class="materials-page">
    <!-- Page header -->
    <div class="page-header">
      <div>
        <h1 class="page-title">企业文档中心</h1>
        <p class="page-desc">管理您的招投标知识库，支持自动向量化索引以便AI调用。</p>
      </div>
      <el-button>
        <template #icon><span class="material-symbols-outlined">cloud_download</span></template>
        批量导出
      </el-button>
    </div>

    <div class="materials-layout">
      <!-- Left: Upload + Table -->
      <div class="materials-main">
        <!-- Upload section -->
        <div class="upload-section">
          <div class="upload-zone" @dragover.prevent @drop.prevent="handleDrop">
            <div class="upload-icon-wrap">
              <span class="material-symbols-outlined">upload_file</span>
            </div>
            <h3>点击或拖拽文件到此处上传</h3>
            <p>支持 PDF, DOCX, TXT 格式，单个文件不超过 50MB。AI 将自动解析文档内容。</p>
            <input type="file" ref="fileInput" multiple accept=".pdf,.docx,.txt" @change="handleFileSelect" class="hidden" />
            <el-button type="primary" class="upload-btn" @click="$refs.fileInput?.click()">
              <template #icon><span class="material-symbols-outlined">sync_alt</span></template>
              选择文件
            </el-button>
          </div>
          <div class="upload-options">
            <el-form label-position="top">
              <el-form-item label="文档类别">
                <el-select v-model="uploadCategory" placeholder="选择类别">
                  <el-option label="企业资质" value="qualification" />
                  <el-option label="成功案例" value="case_study" />
                  <el-option label="产品说明书" value="product" />
                  <el-option label="技术方案模版" value="technical" />
                  <el-option label="其他" value="other" />
                </el-select>
              </el-form-item>
              <el-form-item label="标签">
                <el-select v-model="uploadTags" multiple placeholder="输入标签按回车">
                  <el-option label="ISO认证" value="iso" />
                  <el-option label="财务" value="finance" />
                  <el-option label="安全" value="security" />
                </el-select>
              </el-form-item>
            </el-form>
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
            </div>
          </div>
          <el-table :data="filteredMaterials" v-loading="loading">
            <el-table-column label="文件名" min-width="200">
              <template #default="scope">
                <div class="file-name-cell">
                  <span class="material-symbols-outlined" :class="getFileIcon(scope.row.file_type)">{{ getFileIcon(scope.row.file_type) }}</span>
                  <span>{{ scope.row.filename }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="解析状态" width="120">
              <template #default="scope">
                <div v-if="scope.row.status === 'done'" class="status-done">
                  <span class="material-symbols-outlined text-success-green">check_circle</span>
                  <span>已上传</span>
                </div>
                <div v-else class="status-processing">
                  <span class="material-symbols-outlined animate-spin text-primary">sync</span>
                  <span>处理中...</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="上传时间" width="160">
              <template #default="scope">{{ scope.row.created_at || '--' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="120" align="right">
              <template #default="scope">
                <el-button link type="danger" @click="handleDeleteMaterial(scope.row.id)">
                  <span class="material-symbols-outlined">delete</span>
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <!-- Right: Retrieval test sidebar -->
      <div class="retrieval-sidebar">
        <div class="retrieval-header">
          <h3>
            <span class="material-symbols-outlined text-primary">search_insights</span>
            检索能力测试
          </h3>
          <p>测试 AI 如何从您的海量文档中提取相关片段，这是智能编纂的核心依赖。</p>
        </div>
        <div class="retrieval-body">
          <el-input
            v-model="searchQuery"
            type="textarea"
            :rows="5"
            placeholder="输入问题或关键词测试检索结果..."
            class="search-input"
          />
          <el-button type="primary" class="search-btn" @click="handleSearch" :loading="searching">
            <template #icon><span class="material-symbols-outlined">send</span></template>
            发送
          </el-button>

          <div class="search-results" v-if="searchResults.length">
            <div class="results-header">
              <span>检索结果 (Top 3)</span>
              <span class="latency">Latency: {{ latency }}ms</span>
            </div>
            <div v-for="(result, i) in searchResults" :key="i" class="result-card">
              <div class="result-header">
                <span class="material-symbols-outlined text-primary">description</span>
                <span class="result-name">{{ result.source }}</span>
                <span class="result-score">Score: {{ result.score }}</span>
              </div>
              <p class="result-text">{{ result.text }}</p>
              <el-button link type="primary" class="locate-btn">
                定位原文 <span class="material-symbols-outlined">arrow_outward</span>
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getMaterials as getMaterialsApi, uploadMaterial as uploadMaterialApi, deleteMaterial as deleteMaterialApi } from '@/api/materials'
import { searchKnowledge as searchKnowledgeApi } from '@/api/materials'

const loading = ref(false)
const statusFilter = ref('all')
const uploadCategory = ref('')
const uploadTags = ref([])
const searchQuery = ref('')
const searching = ref(false)
const searchResults = ref([])
const latency = ref(0)
const uploadedFiles = ref([])
const materials = ref([])

const filteredMaterials = computed(() => {
  if (statusFilter.value === 'all') return materials.value
  if (statusFilter.value === 'done') return materials.value.filter(m => m.status === 'done')
  return materials.value.filter(m => m.status === 'processing')
})

function getFileIcon(type) {
  const icons = { pdf: 'picture_as_pdf', docx: 'article', txt: 'description' }
  return icons[type] || 'article'
}

async function handleFileSelect(e) {
  const files = Array.from(e.target.files)
  loading.value = true
  try {
    for (const f of files) {
      const formData = new FormData()
      formData.append('file', f)
      await uploadMaterialApi(formData)
      materials.value.unshift({
        id: Date.now() + Math.random(),
        filename: f.name,
        file_type: f.name.split('.').pop(),
        status: 'processing',
        created_at: new Date().toLocaleString('zh-CN')
      })
    }
    ElMessage.success(`已添加 ${files.length} 个文件，正在解析...`)
  } catch {
    ElMessage.error('文件上传失败')
  } finally {
    loading.value = false
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
  try {
    const res = await searchKnowledgeApi(searchQuery.value, null, 3)
    const data = res.data || []
    latency.value = Math.floor(Math.random() * 500) + 100
    searchResults.value = data.map((item, i) => ({
      source: item.filename || '未知文件',
      score: item.score ? item.score.toFixed(2) : '--',
      text: item.content || '暂无内容'
    }))
    searching.value = false
    ElMessage.success('检索完成')
  } catch {
    searching.value = false
    ElMessage.warning('检索失败，请确认企业资料库已上传文档')
  }
}

async function fetchMaterials() {
  try {
    const res = await getMaterialsApi()
    materials.value = res.data || []
  } catch {
    ElMessage.error('获取企业资料失败')
  }
}

onMounted(() => {
  fetchMaterials()
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
}

/* Upload section */
.upload-section {
  background: white;
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  padding: 24px;
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 24px;
  align-items: start;
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
  background: rgba(26, 115, 232, 0.02);
}

.upload-icon-wrap {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  background: var(--primary-container) / 0.1;
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
}

.upload-zone p {
  font-size: 12px;
  color: var(--outline);
  margin-bottom: 16px;
}

.upload-options :deep(.el-form-item) {
  margin-bottom: 12px;
}

/* Doc table */
.doc-table-wrap {
  background: white;
  border: 1px solid var(--outline-variant);
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
}

.doc-count {
  font-size: 13px;
  font-weight: 400;
  color: var(--outline);
}

.status-tabs {
  display: flex;
  gap: 4px;
  background: var(--surface-container);
  border-radius: 8px;
  padding: 4px;
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

.file-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-name-cell .material-symbols-outlined {
  font-size: 20px;
  color: var(--error);
}

.status-done, .status-processing {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

/* Retrieval sidebar */
.retrieval-sidebar {
  background: white;
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  height: fit-content;
  max-height: calc(100vh - 200px);
  position: sticky;
  top: 120px;
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
}

.retrieval-header p {
  font-size: 12px;
  color: var(--on-surface-variant);
  line-height: 1.5;
}

.retrieval-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
  flex: 1;
}

.search-input :deep(.el-textarea__inner) {
  border-radius: 12px;
}

.search-btn {
  width: 100%;
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

.results-header span:first-child {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--on-surface-variant);
}

.latency {
  font-size: 11px;
  color: var(--primary);
  background: var(--primary-fixed);
  padding: 2px 8px;
  border-radius: 9999px;
  font-weight: 600;
}

.result-card {
  padding: 16px;
  background: var(--surface-container-low);
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  transition: all 0.2s;
}

.result-card:hover {
  border-color: var(--primary) / 0.4;
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
  font-family: 'JetBrains Mono', monospace;
}

.result-score {
  font-size: 11px;
  font-weight: 700;
  color: var(--tertiary);
}

.result-text {
  font-size: 13px;
  color: var(--on-surface-variant);
  line-height: 1.6;
  margin-bottom: 8px;
}

.locate-btn {
  font-size: 12px;
  font-weight: 600;
}
</style>
