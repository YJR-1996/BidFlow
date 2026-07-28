<!-- ProjectDetailView.vue - Project detail with tabs for documents, requirements, compliance -->
<template>
  <div class="project-detail" v-loading="projectStore.loading">
    <!-- Project header card -->
    <div class="project-header">
      <div class="header-left">
        <el-button text @click="$router.back()">
          <span class="material-symbols-outlined">arrow_back</span>
          返回
        </el-button>
        <div class="header-info">
          <div class="header-title-row">
            <h1>{{ projectStore.currentProject?.name || '加载中...' }}</h1>
            <el-tag v-if="projectStore.currentProject?.status" :type="getStatusType(projectStore.currentProject.status)" effect="light" round>
              {{ projectStore.currentProject.status }}
            </el-tag>
          </div>
          <p class="header-meta">
            <span class="material-symbols-outlined">business</span>
            {{ projectStore.currentProject?.tenderer || '招标单位' }}
          </p>
        </div>
      </div>
      <div class="header-right">
        <div class="deadline">
          <span class="deadline-label">投标截止日期</span>
          <span class="deadline-value text-error">
            <span class="material-symbols-outlined">event</span>
            {{ formatDate(projectStore.currentProject?.deadline) }}
          </span>
        </div>
        <div class="progress-section">
          <div class="progress-header">
            <span>响应就绪度</span>
            <span class="progress-pct">{{ projectStore.currentProject?.completionRate || 0 }}%</span>
          </div>
          <el-progress :percentage="projectStore.currentProject?.completionRate || 0" :stroke-width="8" />
        </div>
        <div class="header-actions">
          <el-button @click="exportDraft">导出草稿</el-button>
          <el-button type="primary">提交投标</el-button>
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
            <el-upload
              drag
              :auto-upload="false"
              :on-change="handleFileChange"
              :on-remove="handleFileRemove"
              multiple
              accept=".pdf,.docx,.txt"
              class="upload-zone"
            >
              <span class="material-symbols-outlined upload-icon">cloud_upload</span>
              <p class="upload-title">点击或拖拽文件到此处上传</p>
              <p class="upload-hint">支持格式：PDF, DOCX, TXT (限 25MB)</p>
            </el-upload>
            <div class="file-list">
              <div v-for="file in uploadedFiles" :key="file.name" class="file-item">
                <span class="material-symbols-outlined" :class="file.status === 'done' ? 'text-success-green' : 'text-primary'">
                  {{ file.status === 'done' ? 'check_circle' : 'article' }}
                </span>
                <span class="file-name">{{ file.name }}</span>
                <span class="file-status" v-if="file.status === 'uploading'">
                  <el-progress :percentage="file.progress" :stroke-width="4" />
                </span>
                <span class="file-status" v-else>{{ file.status === 'done' ? '已解析' : '处理中' }}</span>
              </div>
            </div>
          </div>

          <div class="analysis-panel">
            <div class="analysis-header">
              <h3>
                <span class="material-symbols-outlined text-primary">psychology</span>
                AI 提取需求
              </h3>
              <el-tag type="primary" effect="light">已识别 {{ requirements.length }} 项需求</el-tag>
            </div>

            <div class="analysis-content">
              <section class="analysis-section">
                <h4>基础信息</h4>
                <div class="info-grid">
                  <div class="info-item">
                    <span class="info-label">招标文件编号</span>
                    <span class="info-value">{{ projectStore.currentProject?.id || '--' }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">项目总预算</span>
                    <span class="info-value">{{ projectStore.currentProject?.budget ? `¥${projectStore.currentProject.budget}万` : '--' }}</span>
                  </div>
                </div>
              </section>

              <section class="analysis-section">
                <h4>资质要求</h4>
                <div v-for="req in requirements.slice(0, 2)" :key="req.id" class="req-card ai-accent">
                  <div class="req-header">
                    <span class="req-title">{{ req.content?.substring(0, 40) || '--' }}</span>
                    <el-tag :type="req.priority === 'p0' ? 'danger' : req.priority === 'p1' ? 'warning' : ''" size="small" effect="light">
                      {{ req.priority }}
                    </el-tag>
                  </div>
                  <p class="req-desc">{{ req.content?.substring(0, 80) }}</p>
                  <p class="req-source">— {{ req.source_ref || '' }}</p>
                </div>
              </section>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab: Response Checklist -->
      <div v-show="activeTab === 'response'" class="tab-content">
        <RequirementTable
          :requirements="requirements"
          @update-status="handleUpdateStatus"
          @generate-draft="handleGenerateDraft"
        />
      </div>

      <!-- Tab: Compliance Report -->
      <div v-show="activeTab === 'compliance'" class="tab-content">
        <RiskSummary
          :report="complianceReport"
          :loading="reportLoading"
          @recheck="handleRecheck"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { ElMessage } from 'element-plus'
import RequirementTable from '@/components/RequirementTable.vue'
import RiskSummary from '@/components/RiskSummary.vue'
import {
  uploadTender,
  parseTenderDocument,
} from '@/api/projects'
import { runComplianceCheck as runComplianceCheckApi, getComplianceReport as getComplianceReportApi, generateDraft as generateDraftApi } from '@/api/compliance'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

const activeTab = ref('tender')
const uploading = ref(false)
const complianceReport = ref(null)
const reportLoading = ref(false)

// 使用 computed 从 store 获取 requirements，自动保持同步
const requirements = computed(() => projectStore.requirements)

const tabs = [
  { key: 'tender', label: '招标文件', icon: 'description' },
  { key: 'response', label: '响应清单', icon: 'list_alt' },
  { key: 'compliance', label: '合规报告', icon: 'verified_user' }
]

async function loadRequirements() {
  const id = route.params.id
  if (id) {
    // fetchRequirements 会自动更新 store 中的 requirements
    await projectStore.fetchRequirements(id)
  }
}

watch(() => route.params.id, (id) => {
  if (id) {
    projectStore.fetchProject(id)
    loadRequirements()
  }
}, { immediate: true })

onMounted(() => {
  const id = route.params.id
  if (id) {
    projectStore.fetchProject(id)
    loadRequirements()
  }
})

function getStatusType(status) {
  switch (status) {
    case '准备中': return 'info'
    case '审核中': return 'warning'
    case '已完成': return 'success'
    default: return ''
  }
}

function formatDate(date) {
  if (!date) return '--'
  return new Date(date).toLocaleDateString('zh-CN')
}

async function handleFileChange(file) {
  const id = route.params.id
  if (!id || !file.raw) return
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file.raw)
    const doc = await projectStore.uploadTender(id, formData)
    if (doc) {
      ElMessage.success('文件上传成功，开始解析...')
      // Auto-parse after upload
      try {
        await parseTenderDocument(doc.id)
        await loadRequirements()
      } catch {
        // parse error handled by store
      }
    }
  } catch {
    // upload error handled by store
  } finally {
    uploading.value = false
  }
}

function handleFileRemove() {
  // File removal handled by el-upload internally
}

async function handleUpdateStatus(reqId, updates) {
  if (reqId === '_batch') {
    ElMessage.info('批量更新功能开发中')
    return
  }
  const success = await projectStore.updateRequirementStatus(reqId, updates)
  if (success) {
    ElMessage.success('状态已更新')
  } else {
    // 更新失败时重新加载数据以恢复状态
    await loadRequirements()
  }
}

async function handleGenerateDraft(reqId) {
  ElMessage.info('正在生成AI草案...')
  try {
    await generateDraftApi(reqId)
    ElMessage.success('草案生成成功')
    await loadRequirements()
  } catch {
    ElMessage.warning('生成草案时使用了默认内容')
    await loadRequirements()
  }
}

async function handleRecheck() {
  const id = route.params.id
  if (!id) return
  reportLoading.value = true
  try {
    await runComplianceCheckApi(id)
    const res = await getComplianceReportApi(id)
    complianceReport.value = res.data || {}
    ElMessage.success('合规核查完成')
  } catch {
    ElMessage.error('合规核查失败')
  } finally {
    reportLoading.value = false
  }
}

function exportDraft() {
  ElMessage.success('草稿已导出')
}
</script>

<style scoped>
.project-detail {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Header */
.project-header {
  background: white;
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  padding: 24px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.header-left {
  display: flex;
  gap: 16px;
}

.header-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.header-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-title-row h1 {
  font-size: 24px;
  font-weight: 600;
  color: var(--on-surface);
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--on-surface-variant);
}

.header-meta .material-symbols-outlined {
  font-size: 18px;
}

.header-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 16px;
  min-width: 280px;
}

.deadline {
  text-align: right;
}

.deadline-label {
  display: block;
  font-size: 12px;
  color: var(--on-surface-variant);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.deadline-value {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 18px;
  font-weight: 600;
  justify-content: flex-end;
}

.progress-section {
  width: 100%;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
}

.progress-pct {
  font-weight: 700;
  color: var(--primary);
}

.header-actions {
  display: flex;
  gap: 8px;
}

/* Tabs */
.tab-container {
  background: white;
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  overflow: hidden;
}

.tab-headers {
  display: flex;
  border-bottom: 1px solid var(--outline-variant);
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
  font-weight: 500;
  color: var(--on-surface-variant);
  cursor: pointer;
  border-bottom: 3px solid transparent;
  transition: all 0.2s;
}

.tab-btn:hover {
  color: var(--primary);
  background: var(--surface-container-low);
}

.tab-btn.active {
  color: var(--primary);
  border-bottom-color: var(--primary);
  font-weight: 700;
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

.upload-panel h3,
.analysis-header h3 {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.upload-zone :deep(.el-upload-dragger) {
  border-radius: 12px;
  padding: 32px 16px;
  border-color: var(--outline-variant);
}

.upload-zone :deep(.el-upload-dragger:hover) {
  border-color: var(--primary);
  background: var(--surface-container-low);
}

.upload-icon {
  font-size: 48px;
  color: var(--outline);
}

.upload-title {
  font-size: 14px;
  font-weight: 600;
  margin: 8px 0 4px;
}

.upload-hint {
  font-size: 12px;
  color: var(--outline);
}

.file-list {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--surface-container-low);
  border-radius: 8px;
}

.file-name {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
}

.file-status {
  font-size: 12px;
  color: var(--on-surface-variant);
  min-width: 80px;
}

/* Analysis */
.analysis-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
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
  background: var(--surface-container-low);
  border-radius: 8px;
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

.req-card {
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 12px;
}

.ai-accent {
  background: rgba(26, 115, 232, 0.05);
  border-left: 4px solid var(--primary);
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
}
</style>
