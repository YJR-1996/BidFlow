<!-- ComplianceReportView.vue - Compliance report page using shared component -->
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
        <div class="project-selector">
          <span class="selector-label">选择项目：</span>
          <el-select v-model="selectedProjectId" placeholder="请选择项目" @change="handleProjectChange" class="project-select">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </div>
      </div>
      <div class="header-actions">
        <el-button @click="downloadMarkdown" :disabled="!selectedProjectId">
          <template #icon><span class="material-symbols-outlined">description</span></template>
          导出 Markdown
        </el-button>
        <el-button @click="downloadPDF" :disabled="!selectedProjectId">
          <template #icon><span class="material-symbols-outlined">picture_as_pdf</span></template>
          导出 PDF
        </el-button>
        <el-button type="primary" :loading="rechecking" @click="handleRecheck" :disabled="!selectedProjectId">
          <template #icon><span class="material-symbols-outlined" :class="{ 'animate-spin': rechecking }">refresh</span></template>
          {{ rechecking ? '核查中...' : '重新核查' }}
        </el-button>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!selectedProjectId" class="empty-project-state">
      <span class="material-symbols-outlined">folder_open</span>
      <h2>请选择项目</h2>
      <p>从上方下拉菜单中选择一个项目以查看合规核查报告</p>
    </div>

    <!-- Shared compliance report component -->
    <ComplianceReport
      v-else
      :report="complianceReportData"
      :loading="rechecking"
      @apply-suggestion="applySuggestion"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { ElMessage } from 'element-plus'
import { runComplianceCheck as runComplianceCheckApi, getComplianceReport as getComplianceReportApi, downloadReportMarkdown } from '@/api/compliance'
import ComplianceReport from '@/components/ComplianceReport.vue'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

const rechecking = ref(false)
const complianceReportData = ref(null)
const selectedProjectId = ref(null)
const selectedProjectName = ref('')
const lastUpdate = ref(new Date().toLocaleString('zh-CN'))

const projectName = computed(() => selectedProjectName.value || '选择项目')
const projects = computed(() => projectStore.projects)

function handleProjectChange(projectId) {
  const project = projects.value.find(p => String(p.id) === String(projectId))
  if (project) {
    selectedProjectId.value = project.id
    selectedProjectName.value = project.name
    complianceReportData.value = null
    loadComplianceReport()
  }
}

async function loadComplianceReport() {
  if (!selectedProjectId.value) return
  try {
    const res = await getComplianceReportApi(selectedProjectId.value)
    const data = res.data || res
    complianceReportData.value = data || {}
  } catch {
    complianceReportData.value = null
  }
}

async function handleRecheck() {
  if (!selectedProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  rechecking.value = true
  try {
    await runComplianceCheckApi(selectedProjectId.value)
    const res = await getComplianceReportApi(selectedProjectId.value)
    const data = res.data || res
    complianceReportData.value = data || {}
    lastUpdate.value = new Date().toLocaleString('zh-CN')
    ElMessage.success('重新核查完成')
  } catch (error) {
    ElMessage.error(error.message || '重新核查失败')
  } finally {
    rechecking.value = false
  }
}

async function downloadMarkdown() {
  if (!selectedProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  try {
    const blob = await downloadReportMarkdown(selectedProjectId.value)
    const url = window.URL.createObjectURL(new Blob([blob]))
    const a = document.createElement('a')
    a.href = url
    a.download = `compliance-report-${selectedProjectId.value}.md`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
    ElMessage.success('报告已导出')
  } catch (error) {
    ElMessage.error(error.message || '导出失败')
  }
}

function downloadPDF() {
  ElMessage.info('PDF 导出功能开发中，请使用 Markdown 导出')
}

function applySuggestion(risk) {
  ElMessage.success(`已应用建议：${risk.title}（自动修复功能开发中）`)
}

onMounted(async () => {
  await projectStore.fetchProjects()

  const projectId = route.params.id
  if (projectId) {
    const project = projectStore.projects.find(p => String(p.id) === String(projectId))
    if (project) {
      selectedProjectId.value = project.id
      selectedProjectName.value = project.name
      loadComplianceReport()
    }
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

.project-selector {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

.selector-label {
  font-size: 13px;
  color: var(--on-surface-variant);
  font-weight: 500;
}

.project-select {
  width: 280px;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* Empty state */
.empty-project-state {
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

.empty-project-state .material-symbols-outlined {
  font-size: 64px;
  color: var(--outline);
  margin-bottom: 16px;
}

.empty-project-state h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--on-surface);
  margin-bottom: 8px;
}

.empty-project-state p {
  font-size: 14px;
  color: var(--on-surface-variant);
}

/* Utility */
.text-primary { color: var(--primary); }

/* Responsive */
@media (max-width: 768px) {
  .report-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>