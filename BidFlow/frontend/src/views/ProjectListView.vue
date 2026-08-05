<!-- ProjectListView.vue - Project management workspace -->
<template>
  <div class="project-list">
    <!-- Page Header -->
    <div class="page-header">
      <div class="header-info">
        <h1>项目管理</h1>
        <p class="header-subtitle">管理所有投标项目，查看项目进度、风险和合规状态</p>
      </div>
      <div class="header-actions">
        <el-button @click="$router.push('/analytics')">
          <template #icon><span class="material-symbols-outlined">analytics</span></template>
          详细报表
        </el-button>
        <el-button type="primary" @click="$router.push('/new-project')">
          <template #icon><span class="material-symbols-outlined">add</span></template>
          新建项目
        </el-button>
      </div>
    </div>

    <!-- Statistics Row (clickable filters) -->
    <div class="stats-row">
      <div
        v-for="stat in clickableStats"
        :key="stat.label"
        :class="['stat-card', { 'is-risk': stat.isRisk, 'is-active': activeFilter === stat.filterValue }]"
        @click="applyStatFilter(stat)"
      >
        <div class="stat-info">
          <p class="stat-label">{{ stat.label }}</p>
          <p :class="['stat-value', { 'is-error': stat.isRisk }]">{{ stat.value }}</p>
        </div>
        <span
          :class="['stat-icon', stat.isRisk ? 'icon-error' : 'icon-primary']"
          class="material-symbols-outlined"
        >{{ stat.icon }}</span>
        <span v-if="activeFilter === stat.filterValue" class="filter-indicator">
          <span class="material-symbols-outlined">check_circle</span>
        </span>
      </div>
    </div>

    <!-- Quick Actions Bar -->
    <div class="quick-actions">
      <span class="quick-label">快捷操作：</span>
      <el-button
        v-if="activeFilter"
        size="small"
        @click="clearFilter"
      >
        <template #icon><span class="material-symbols-outlined">close</span></template>
        清除筛选
      </el-button>
      <el-button size="small" @click="$router.push('/compliance')">
        <template #icon><span class="material-symbols-outlined">fact_check</span></template>
        合规核查
      </el-button>
      <el-button size="small" @click="$router.push('/company-materials')">
        <template #icon><span class="material-symbols-outlined">description</span></template>
        资料库
      </el-button>
    </div>

    <!-- Main Content Area -->
    <div class="table-container">
      <!-- Filter Bar -->
      <div class="filter-bar">
        <div class="filter-left">
          <el-input
            v-model="projectStore.filters.search"
            placeholder="按项目名称筛选..."
            class="filter-search"
            clearable
          >
            <template #prefix><span class="material-symbols-outlined text-sm">search</span></template>
          </el-input>
          <el-select v-model="projectStore.filters.status" placeholder="状态" class="filter-select" clearable>
            <el-option label="全部" value="all" />
            <el-option label="准备中" value="准备中" />
            <el-option label="审核中" value="审核中" />
            <el-option label="已完成" value="已完成" />
          </el-select>
        </div>
      </div>

      <!-- Data display -->
      <el-table
        :data="pagedProjects"
        v-loading="projectStore.loading"
        class="bidflow-table"
        :header-cell-style="{ background: '#f7f9fc', color: '#414754', fontWeight: 'bold' }"
      >
        <el-table-column label="项目名称" min-width="250">
          <template #default="scope">
            <div class="project-name">
              <span class="material-symbols-outlined text-primary-container">folder_managed</span>
              <div>
                <el-link type="primary" class="project-link" @click="goDetail(scope.row)">{{ scope.row.name }}</el-link>
                <span class="project-id">{{ scope.row.id }}</span>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="120">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)" effect="light" class="status-tag">
              {{ scope.row.status }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="完成度" width="180">
          <template #default="scope">
            <div class="progress-col">
              <el-progress
                :percentage="scope.row.completionRate || 0"
                :color="getProgressColor(scope.row.completionRate || 0)"
                :stroke-width="8"
              />
              <span class="progress-text">已完成 {{ scope.row.completionRate || 0 }}%</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="风险数量" width="120">
          <template #default="scope">
            <div v-if="scope.row.risk_count > 0" class="risk-badge">
              <span class="material-symbols-outlined">warning</span>
              <span>{{ scope.row.risk_count }}</span>
            </div>
            <span v-else class="no-risk">无风险</span>
          </template>
        </el-table-column>

        <el-table-column label="截止日期" width="140">
          <template #default="scope">
            <div v-if="scope.row.deadline" class="deadline-cell">
              <span class="material-symbols-outlined deadline-icon">event</span>
              <span
                class="deadline-text"
                :class="{
                  'deadline-urgent': deadlineInfo(scope.row.deadline).urgent,
                  'deadline-expired': deadlineInfo(scope.row.deadline).expired,
                }"
              >{{ deadlineInfo(scope.row.deadline).text }}</span>
            </div>
            <span v-else class="no-deadline">--</span>
          </template>
        </el-table-column>

        <el-table-column label="创建时间" width="110">
          <template #default="scope">
            <span class="created-text">{{ relativeTime(scope.row.created_at) }}</span>
          </template>
        </el-table-column>

        <el-table-column align="right" label="操作" width="180">
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
        <span class="table-info">{{ rangeText(filteredList.length) }}</span>
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="filteredList.length"
          background
          layout="prev, pager, next"
        />
      </div>
    </div>

    <!-- Delete confirmation dialog -->
    <el-dialog v-model="deleteDialogVisible" title="确认删除" width="400px" center class="delete-dialog">
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
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { parseServerDate } from '@/utils/date'
import { ElMessage } from 'element-plus'
import { usePagination } from '@/composables/usePagination'

const router = useRouter()
const projectStore = useProjectStore()

const { currentPage, pageSize, paged, rangeText } = usePagination(10)

const deleteDialogVisible = ref(false)
const selectedProject = ref(null)
const activeFilter = ref('')

// Make stats cards clickable for filtering
const clickableStats = computed(() => {
  const stats = projectStore.stats
  return stats.map(stat => {
    let filterValue = ''
    let filterKey = ''
    if (stat.label === '全部项目') { filterValue = 'all'; filterKey = '' }
    else if (stat.label === '准备中') { filterValue = '准备中'; filterKey = 'status' }
    else if (stat.label === '审核中') { filterValue = '审核中'; filterKey = 'status' }
    else if (stat.label === '已完成') { filterValue = '已完成'; filterKey = 'status' }
    else if (stat.label === '待处理风险') { filterValue = 'risk'; filterKey = 'hasRisk' }
    return { ...stat, filterValue, filterKey }
  })
})

// Apply filter from stat card click
function applyStatFilter(stat) {
  if (stat.filterKey === 'status') {
    projectStore.filters.status = stat.filterValue
    activeFilter.value = stat.filterValue
  } else if (stat.filterKey === 'hasRisk') {
    projectStore.filters.status = 'all'
    activeFilter.value = 'risk'
  } else {
    projectStore.filters.status = 'all'
    activeFilter.value = ''
  }
  currentPage.value = 1
}

function clearFilter() {
  projectStore.filters.status = 'all'
  activeFilter.value = ''
  currentPage.value = 1
}

// Apply additional risk filter
const filteredList = computed(() => {
  if (activeFilter.value === 'risk') {
    return projectStore.filteredProjects.filter(p => p.risk_count > 0)
  }
  return projectStore.filteredProjects
})

const pagedProjects = computed(() => paged(filteredList.value))

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

// 截止日期倒计时：≤3 天标红，已过期灰显
function deadlineInfo(d) {
  if (!d) return { text: '--', urgent: false, expired: false }
  const target = parseServerDate(d)
  if (!target) return { text: '--', urgent: false, expired: false }
  const diffDays = Math.ceil((target - new Date()) / 86400000)
  if (diffDays < 0) return { text: `已过期 ${Math.abs(diffDays)} 天`, urgent: false, expired: true }
  if (diffDays === 0) return { text: '今天截止', urgent: true, expired: false }
  if (diffDays <= 3) return { text: `剩 ${diffDays} 天`, urgent: true, expired: false }
  return { text: target.toLocaleDateString('zh-CN'), urgent: false, expired: false }
}

// 相对时间：刚刚 / N 分钟前 / N 小时前 / N 天前 / 日期
function relativeTime(d) {
  if (!d) return '--'
  const past = parseServerDate(d)
  if (!past) return '--'
  const diffMs = new Date() - past
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} 天前`
  return past.toLocaleDateString('zh-CN')
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
  gap: 20px;
}

/* Page Header */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--outline-variant);
}

.header-info h1 {
  font-size: 28px;
  font-weight: 700;
  color: var(--on-surface);
  margin: 0 0 4px 0;
}

.header-subtitle {
  font-size: 14px;
  color: var(--on-surface-variant);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

/* Stats Row */
.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
}

.stat-card {
  background: var(--surface-container-lowest);
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  border-left: 4px solid var(--primary);
  transition: all 0.2s;
  cursor: pointer;
  position: relative;
}

.stat-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.stat-card.is-active {
  border-left-color: var(--primary);
  background: var(--primary-fixed);
}

.stat-card.is-risk {
  border-left-color: var(--error);
}

.stat-card.is-active.is-risk {
  background: var(--error-container);
}

.filter-indicator {
  position: absolute;
  top: 8px;
  right: 8px;
  color: var(--primary);
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--on-surface-variant);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--on-surface);
  letter-spacing: -0.02em;
  line-height: 1.25;
  margin: 0;
}

.stat-value.is-error {
  color: var(--error);
}

.stat-icon {
  padding: 8px;
  border-radius: 8px;
  font-size: 24px;
}

.stat-icon.icon-primary {
  background: var(--primary-fixed);
  color: var(--on-primary-fixed);
}

.stat-icon.icon-error {
  background: var(--error-container);
  color: var(--on-error-container);
}

/* Quick Actions */
.quick-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--surface-container);
  border-radius: 8px;
  font-size: 13px;
}

.quick-label {
  color: var(--on-surface-variant);
  font-weight: 600;
}

/* Table */
.table-container {
  background: var(--surface-container-lowest);
  border: 1px solid var(--outline-variant);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  padding: 20px 24px;
  border-bottom: 1px solid var(--outline-variant);
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

.bidflow-table :deep(.el-table th) {
  font-size: 13px;
  font-weight: 700;
  color: var(--on-surface-variant);
}

.bidflow-table :deep(.el-table__row:hover) {
  background: var(--surface-container-low) !important;
}

.project-name {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.project-name .material-symbols-outlined {
  font-size: 24px;
}

.project-link {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.3;
}

.project-id {
  display: block;
  font-size: 11px;
  color: var(--outline);
  font-family: 'JetBrains Mono', monospace;
  line-height: 1.2;
}

.status-tag {
  border-radius: 4px;
  font-weight: 600;
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
  font-size: 14px;
}

.no-risk {
  color: var(--outline);
  font-size: 13px;
}

/* A 方案：截止日期 + 创建时间（替代无信息量的"负责人"列） */
.deadline-cell { display: flex; align-items: center; gap: 5px; }
.deadline-icon { font-size: 15px; color: var(--outline); }
.deadline-text { font-size: 13px; color: var(--on-surface); }
.deadline-urgent { color: #ba1a1a !important; font-weight: 600; }
.deadline-expired { color: var(--outline) !important; text-decoration: line-through; }
.no-deadline { color: var(--outline); font-size: 13px; }
.created-text { font-size: 13px; color: var(--on-surface-variant); }

.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-top: 1px solid var(--outline-variant);
  background: var(--surface-container-low);
}

.table-info {
  font-size: 14px;
  color: var(--outline);
}

.delete-dialog :deep(.el-dialog) {
  border-radius: 12px;
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

/* Utility classes */
.text-primary-container { color: var(--primary-container); }
.text-sm { font-size: 14px; }

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: 16px;
  }

  .filter-left {
    flex-direction: column;
    width: 100%;
  }

  .filter-search,
  .filter-select {
    max-width: none;
    width: 100%;
  }
}
</style>