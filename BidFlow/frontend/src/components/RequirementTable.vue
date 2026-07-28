<!-- RequirementTable.vue - Requirement management with status, priority, and AI draft -->
<template>
  <div class="requirement-table">
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
        <label>状态</label>
        <el-select v-model="filters.status" placeholder="所有状态" clearable style="width: 140px">
          <el-option label="所有状态" value="" />
          <el-option label="待处理" value="待处理" />
          <el-option label="处理中" value="处理中" />
          <el-option label="已完成" value="已完成" />
          <el-option label="待评审" value="待评审" />
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

      <el-table-column label="需求内容" min-width="300">
        <template #default="scope">
          <div class="req-content">
            <p>{{ scope.row.content || scope.row.title || '--' }}</p>
            <p v-if="scope.row.description" class="req-desc">{{ scope.row.description }}</p>
            <p v-if="!scope.row.content && scope.row.title" class="req-desc">{{ scope.row.source_text || '' }}</p>
          </div>
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

      <el-table-column label="状态" width="110" align="center">
        <template #default="scope">
          <el-select :model-value="scope.row.status" size="small" @change="(val) => emit('update-status', scope.row.id, { status: val })">
            <el-option label="待处理" value="待处理" />
            <el-option label="处理中" value="处理中" />
            <el-option label="已完成" value="已完成" />
            <el-option label="待评审" value="待评审" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="负责人" width="120">
        <template #default="scope">
          <div v-if="scope.row.owner" class="owner-info">
            <el-avatar :size="20">{{ scope.row.owner.charAt(0) }}</el-avatar>
            <span>{{ scope.row.owner }}</span>
          </div>
          <span v-else class="no-owner">未分配</span>
        </template>
      </el-table-column>

      <el-table-column label="风险" width="72" align="center">
        <template #default="scope">
          <el-tag v-if="scope.row.risk_level === '高'" type="danger" size="small" effect="light">高</el-tag>
          <el-tag v-else-if="scope.row.risk_level === '中'" type="warning" size="small" effect="light">中</el-tag>
          <el-tag v-else-if="scope.row.risk_level === '低'" type="success" size="small" effect="light">低</el-tag>
          <span v-else class="no-risk">-</span>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="120" align="right" fixed="right">
        <template #default="scope">
          <div class="action-btns">
            <el-button size="small" type="primary" link @click="emit('generate-draft', scope.row.id)">
              <span class="material-symbols-outlined">auto_awesome</span>
            </el-button>
            <el-button size="small" type="primary" link @click="editRequirement(scope.row)">
              <span class="material-symbols-outlined">edit</span>
            </el-button>
            <el-button size="small" type="primary" link @click="viewDetail(scope.row)">
              <span class="material-symbols-outlined">visibility</span>
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- Empty state -->
    <el-empty v-if="filteredRequirements.length === 0 && !loading" description="未找到符合条件的 requirement" />

    <!-- Selection bar -->
    <div v-if="selected.length > 0" class="selection-bar">
      <span>已选中 <strong>{{ selected.length }}</strong> 项</span>
      <el-button size="small" @click="emit('update-status', '_batch', {})">批量更新状态</el-button>
      <el-button size="small" type="danger" @click="deleteSelected">批量删除</el-button>
    </div>

    <!-- Footer stats -->
    <div class="table-footer">
      <div class="footer-stats">
        <span>总计: <strong>{{ requirements.length }}</strong></span>
        <span>已完成: <strong class="text-success-green">{{ doneCount }}</strong></span>
        <span>待处理: <strong class="text-warning-amber">{{ pendingCount }}</strong></span>
      </div>
      <span class="footer-page">第 1 页，共 {{ Math.ceil(requirements.length / 20) }} 页</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  requirements: { type: Array, default: () => [] }
})

const emit = defineEmits(['update-status', 'generate-draft'])

const filters = ref({
  category: '',
  status: '',
  priority: '',
  keyword: ''
})

const loading = ref(false)
const selected = ref([])

const filteredRequirements = computed(() => {
  return props.requirements.filter(r => {
    if (filters.value.category && r.category !== filters.value.category) return false
    if (filters.value.status && r.status !== filters.value.status) return false
    if (filters.value.priority && r.priority !== filters.value.priority) return false
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

function handleSelectionChange(items) {
  selected.value = items
}

function getCategoryType(cat) {
  const map = { 技术: 'primary', 商务: '', 资格: 'info', 评分: 'warning' }
  return map[cat] || ''
}

function getCategoryLabel(cat) {
  return cat || '其他'
}

function editRequirement(row) {
  const content = row.content || row.title || ''
  ElMessage.info(`编辑需求: ${content.substring(0, 30)}`)
}

function viewDetail(row) {
  const content = row.content || row.title || ''
  ElMessage.info(`查看需求详情: ${content.substring(0, 30)}`)
}

function deleteSelected() {
  ElMessage.warning('批量删除功能开发中')
}
</script>

<style scoped>
.requirement-table {
  display: flex;
  flex-direction: column;
  gap: 16px;
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
}

.req-desc {
  font-size: 12px;
  color: var(--on-surface-variant);
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

.owner-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.no-owner {
  font-size: 13px;
  font-style: italic;
  color: var(--outline);
  opacity: 0.6;
}

.no-risk {
  color: var(--outline);
  font-size: 13px;
}

.action-btns {
  display: flex;
  gap: 4px;
  justify-content: flex-end;
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
</style>
