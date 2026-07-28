<!-- ProjectListView.vue - Project list with stats, filters, and CRUD -->
<template>
  <div class="project-list">
    <!-- Statistics row -->
    <div class="stats-row">
      <div v-for="stat in stats" :key="stat.label" class="stat-card" :class="{ 'is-risk': stat.isRisk }">
        <div class="stat-info">
          <span class="stat-label">{{ stat.label }}</span>
          <span class="stat-value" :class="{ 'text-error': stat.isRisk }">{{ stat.value }}</span>
        </div>
        <div class="stat-icon" :class="stat.isRisk ? 'bg-error-container' : 'bg-primary-fixed'">
          <span class="material-symbols-outlined">{{ stat.icon }}</span>
        </div>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="filter-bar">
      <div class="filter-left">
        <el-input
          v-model="projectStore.filters.search"
          placeholder="按项目名称筛选..."
          class="filter-search"
          clearable
        >
          <template #prefix><span class="material-symbols-outlined">search</span></template>
        </el-input>
        <el-select v-model="projectStore.filters.status" placeholder="状态" class="filter-select" clearable>
          <el-option label="全部" value="all" />
          <el-option label="准备中" value="准备中" />
          <el-option label="审核中" value="审核中" />
          <el-option label="已完成" value="已完成" />
        </el-select>
      </div>
      <el-button type="primary" @click="$router.push('/new-project')">
        <template #icon><span class="material-symbols-outlined">add</span></template>
        新建项目
      </el-button>
    </div>

    <!-- Data table -->
    <div class="table-container">
      <el-table
        :data="projectStore.filteredProjects"
        v-loading="projectStore.loading"
        class="bidflow-table"
        :header-cell-style="{ background: '#f7f9fc', color: '#414754', fontWeight: 'bold' }"
      >
        <el-table-column label="项目名称" min-width="250">
          <template #default="scope">
            <div class="project-name">
              <span class="material-symbols-outlined text-primary-container">folder_managed</span>
              <div>
                <el-link type="primary" @click="goDetail(scope.row)">{{ scope.row.name }}</el-link>
                <span class="project-id">{{ scope.row.id }}</span>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="120">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)" effect="light" round>
              {{ scope.row.status }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="完成度" width="180">
          <template #default="scope">
            <div class="progress-col">
              <el-progress
                :percentage="scope.row.completionRate"
                :color="getProgressColor(scope.row.completionRate)"
                :stroke-width="8"
              />
              <span class="progress-text">{{ scope.row.completionRate }}%</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="风险数量" width="120">
          <template #default="scope">
            <div v-if="scope.row.risk_count > 0" class="risk-badge">
              <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">warning</span>
              <span>{{ scope.row.risk_count }}</span>
            </div>
            <span v-else class="no-risk">无风险</span>
          </template>
        </el-table-column>

        <el-table-column label="负责人" width="150">
          <template #default="scope">
            <div class="owner-info">
              <el-avatar :size="24">{{ scope.row.owner?.charAt(0) }}</el-avatar>
              <span>{{ scope.row.owner }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column align="right" label="操作" width="200">
          <template #default="scope">
            <el-button link type="primary" @click="goDetail(scope.row)">查看详情</el-button>
            <el-button link type="danger" @click="confirmDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty description="未找到符合条件的项目">
            <el-button type="primary" @click="$router.push('/new-project')">创建首个项目</el-button>
          </el-empty>
        </template>
      </el-table>

      <!-- Pagination -->
      <div class="table-footer">
        <span class="table-info">显示第 1 到 {{ projectStore.filteredProjects.length }} 条，共 {{ projectStore.filteredProjects.length }} 条</span>
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="10"
          :total="projectStore.filteredProjects.length"
          background
          layout="prev, pager, next"
        />
      </div>
    </div>

    <!-- Delete confirmation dialog -->
    <el-dialog v-model="deleteDialogVisible" title="确认删除" width="400px" center>
      <div class="delete-confirm">
        <span class="material-symbols-outlined delete-icon">delete_forever</span>
        <p>您确定要删除 <strong>{{ selectedProject?.name }}</strong> 吗？此操作无法撤销。</p>
      </div>
      <template #footer>
        <el-button @click="deleteDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="handleDelete">确认删除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { ElMessage } from 'element-plus'

const router = useRouter()
const projectStore = useProjectStore()

const currentPage = ref(1)
const deleteDialogVisible = ref(false)
const selectedProject = ref(null)

// Use store's computed stats
const stats = computed(() => projectStore.stats)

function getStatusType(status) {
  switch (status) {
    case '准备中': return 'info'
    case '审核中': return 'warning'
    case '已完成': return 'success'
    default: return ''
  }
}

function getProgressColor(progress) {
  if (progress < 30) return '#414754'
  if (progress < 100) return '#1a73e8'
  return '#286c00'
}

function goDetail(row) {
  router.push(`/project/${row.id}`)
}

function confirmDelete(row) {
  selectedProject.value = row
  deleteDialogVisible.value = true
}

async function handleDelete() {
  if (!selectedProject.value) return
  await projectStore.removeProject(selectedProject.value.id)
  deleteDialogVisible.value = false
  ElMessage.success('项目已成功移除')
}

onMounted(() => {
  projectStore.fetchProjects()
})
</script>

<style scoped>
.project-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Stats */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
}

.stat-card {
  background: white;
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  padding: 20px 24px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  transition: box-shadow 0.2s;
}

.stat-card.is-risk {
  border-left: 4px solid var(--error);
}

.stat-card:not(.is-risk) {
  border-left: 4px solid var(--primary);
}

.stat-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
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

.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon .material-symbols-outlined {
  font-size: 24px;
}

/* Filter bar */
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: white;
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  padding: 20px 24px;
}

.filter-left {
  display: flex;
  gap: 16px;
  flex: 1;
}

.filter-search {
  max-width: 300px;
}

.filter-select {
  width: 140px;
}

/* Table */
.table-container {
  background: white;
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  overflow: hidden;
}

.bidflow-table :deep(.el-table__row:hover) {
  background: var(--surface-container-low) !important;
}

.bidflow-table :deep(.el-table th) {
  font-size: 13px;
  font-weight: 600;
}

.project-name {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.project-name .material-symbols-outlined {
  font-size: 24px;
  color: var(--primary-container);
}

.project-id {
  display: block;
  font-size: 11px;
  color: var(--outline);
  font-family: 'JetBrains Mono', monospace;
}

.progress-col {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.progress-text {
  font-size: 11px;
  color: var(--outline);
}

.risk-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--error);
  font-weight: 600;
}

.risk-badge .material-symbols-outlined {
  font-size: 18px;
}

.no-risk {
  color: var(--outline);
  font-size: 13px;
}

.owner-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-top: 1px solid var(--outline-variant);
  background: var(--surface-container-low);
}

.table-info {
  font-size: 13px;
  color: var(--outline);
}

.delete-confirm {
  text-align: center;
  padding: 16px;
}

.delete-icon {
  font-size: 48px;
  color: var(--error);
  margin-bottom: 16px;
}

.delete-confirm p {
  font-size: 14px;
  color: var(--on-surface-variant);
}

.delete-confirm strong {
  color: var(--on-surface);
}
</style>
