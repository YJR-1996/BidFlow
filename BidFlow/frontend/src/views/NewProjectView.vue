<!-- NewProjectView.vue - New project creation form -->
<template>
  <div class="new-project-page">
    <div class="page-layout">
      <!-- Left: Form Area (8 cols) -->
      <div class="form-area">
        <div class="form-card">
          <header class="form-header">
            <h2>新建招标项目</h2>
            <p>请填写项目基本信息，AI将根据这些信息辅助您进行文件编制与核查</p>
          </header>

          <el-form
            ref="formRef"
            :model="form"
            :rules="rules"
            label-position="top"
            @submit.prevent="handleSubmit"
          >
            <!-- Project Name -->
            <el-form-item label="项目名称" prop="name">
              <el-input
                v-model="form.name"
                placeholder="请输入招标项目全称"
                size="large"
              />
            </el-form-item>

            <!-- Agency & Deadline -->
            <div class="form-row">
              <el-form-item label="招标单位" prop="tenderer" class="form-half">
                <el-input
                  v-model="form.tenderer"
                  placeholder="请输入招标人名称"
                  size="large"
                />
              </el-form-item>
              <el-form-item label="截止日期" prop="deadline" class="form-half">
                <el-date-picker
                  v-model="form.deadline"
                  type="date"
                  placeholder="请选择截止日期"
                  size="large"
                  value-format="YYYY-MM-DD"
                  style="width: 100%"
                />
              </el-form-item>
            </div>

            <!-- Budget -->
            <el-form-item label="预算金额 (万元)">
              <el-input-number
                v-model="form.budget"
                placeholder="请输入预计金额"
                :min="0"
                :precision="2"
                size="large"
                controls-position="right"
                style="width: 100%"
              />
            </el-form-item>

            <!-- Description -->
            <el-form-item label="项目描述" prop="description">
              <el-input
                v-model="form.description"
                type="textarea"
                :rows="4"
                placeholder="请输入项目背景及核心需求..."
                :maxlength="500"
                resize="none"
              />
              <div class="description-hint-row">
                <p class="description-hint">
                  <span class="material-symbols-outlined">tips_and_updates</span>
                  AI 将通过此描述优化文件生成质量
                </p>
                <span class="char-count">{{ form.description.length }} / 500</span>
              </div>
            </el-form-item>

            <!-- Actions -->
            <div class="form-actions">
              <el-button
                type="primary"
                size="large"
                class="submit-btn"
                :loading="submitting"
                @click="handleSubmit"
              >
                {{ submitting ? '正在创建...' : '提交项目' }}
              </el-button>
              <el-button size="large" class="cancel-btn" @click="handleCancel">取消</el-button>
            </div>
          </el-form>
        </div>
      </div>

      <!-- Right: Info/Process Card (4 cols) -->
      <div class="info-sidebar">
        <!-- AI Assistant Info Card -->
        <div class="info-card ai-card">
          <div class="ai-decoration">
            <span class="material-symbols-outlined">contract</span>
          </div>
          <div class="ai-content">
            <div class="ai-header">
              <div class="ai-icon-wrap">
                <span class="material-symbols-outlined">bolt</span>
              </div>
              <div>
                <h3>BidFlow AI 智囊</h3>
                <p>实时指导与生成建议</p>
              </div>
            </div>
            <p class="ai-desc">创建项目后，系统将立即开启：</p>
            <ul class="ai-features">
              <li>
                <span class="material-symbols-outlined text-success-green">check_circle</span>
                <span><b>模版匹配：</b>基于行业自动推荐招标模版</span>
              </li>
              <li>
                <span class="material-symbols-outlined text-success-green">check_circle</span>
                <span><b>合规预警：</b>自动对照最新行业法律法规</span>
              </li>
              <li>
                <span class="material-symbols-outlined text-success-green">check_circle</span>
                <span><b>进度追踪：</b>多维度跟进招标生命周期</span>
              </li>
            </ul>
          </div>
        </div>

        <!-- Step Guide Card -->
        <div class="info-card">
          <h3>编制流程图</h3>
          <div class="process-steps">
            <div v-for="(step, i) in steps" :key="i" class="process-step" :class="{ active: i <= activeStep }">
              <div class="step-dot" :class="{ filled: i <= activeStep }">
                {{ i + 1 }}
              </div>
              <div class="step-info">
                <h4>{{ step.title }}</h4>
                <p>{{ step.desc }}</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Info Card -->
        <div class="info-card tip-card">
          <div class="tip-header">
            <span class="material-symbols-outlined text-primary">info</span>
            <span>注意事项</span>
          </div>
          <p>预算金额建议录入准确数值，以便 AI 自动计算并匹配最适合的招标方式（公开招标、邀请招标或竞争性谈判等）。</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { ElMessage } from 'element-plus'

const router = useRouter()
const projectStore = useProjectStore()
const formRef = ref(null)
const submitting = ref(false)
const activeStep = ref(0)

const form = reactive({
  name: '',
  tenderer: '',
  deadline: '',
  budget: null,
  description: ''
})

const rules = {
  name: [
    { required: true, message: '项目名称为必填项', trigger: 'blur' }
  ],
  tenderer: [
    { required: true, message: '招标单位为必填项', trigger: 'blur' }
  ],
  deadline: [
    { required: true, message: '截止日期为必填项', trigger: 'change' }
  ],
  description: [
    { max: 500, message: '描述不能超过 500 个字符', trigger: 'blur' }
  ]
}

const steps = [
  { title: '填写项目概况', desc: '录入基础信息，确定项目基调' },
  { title: '上传参考资料', desc: '提供过往案例或技术规格书' },
  { title: 'AI 自动生成', desc: '生成技术需求、评分标准及合同' },
  { title: '专家人工核查', desc: '在线协作，完成最终定稿' }
]

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return

    submitting.value = true
    try {
      await projectStore.createProject(form)
      ElMessage.success('项目已成功创建！')
      router.push('/projects')
    } catch {
      ElMessage.error('项目创建失败')
    } finally {
      submitting.value = false
    }
  })
}

function handleCancel() {
  router.back()
}
</script>

<style scoped>
.new-project-page {
  min-height: calc(100vh - 96px);
}

.page-layout {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 32px;
}

/* Form area */
.form-area {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.form-card {
  background: var(--surface-container-lowest);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 32px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.form-header {
  margin-bottom: 32px;
}

.form-header h2 {
  font-size: 32px;
  font-weight: 700;
  color: var(--on-surface);
  margin-bottom: 8px;
  letter-spacing: -0.02em;
}

.form-header p {
  font-size: 16px;
  color: var(--on-surface-variant);
  margin: 0;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.form-half {
  margin-bottom: 0;
}

.description-hint-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 4px;
  margin-top: 4px;
}

.description-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--on-surface-variant);
  margin: 0;
}

.description-hint .material-symbols-outlined {
  font-size: 16px;
}

.char-count {
  font-size: 12px;
  color: var(--on-surface-variant);
}

.form-actions {
  display: flex;
  gap: 16px;
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid var(--outline-variant);
  align-items: center;
}

.submit-btn {
  flex: 1;
  height: 48px;
  font-size: 16px;
  font-weight: 700;
}

.cancel-btn {
  height: 48px;
  padding: 0 32px;
  font-weight: 500;
}

/* Sidebar */
.info-sidebar {
  display: flex;
  flex-direction: column;
  gap: 24px;
  position: sticky;
  top: 96px;
}

.info-card {
  background: var(--surface-container-lowest);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.info-card h3 {
  font-size: 18px;
  font-weight: 700;
  color: var(--on-surface);
  margin-bottom: 20px;
}

/* AI card */
.ai-card {
  background: rgba(26, 115, 232, 0.05);
  border-color: rgba(26, 115, 232, 0.2);
  position: relative;
  overflow: hidden;
  box-shadow: inset 0 0 15px rgba(26, 115, 232, 0.05);
}

.ai-decoration {
  position: absolute;
  right: -16px;
  bottom: -16px;
  opacity: 0.08;
  pointer-events: none;
}

.ai-decoration .material-symbols-outlined {
  font-size: 96px;
  color: var(--primary);
}

.ai-content {
  position: relative;
  z-index: 1;
}

.ai-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.ai-icon-wrap {
  width: 40px;
  height: 40px;
  background: var(--primary-container);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ai-icon-wrap .material-symbols-outlined {
  font-size: 24px;
  color: white;
  font-variation-settings: 'FILL' 1;
}

.ai-header h3 {
  font-size: 16px;
  font-weight: 700;
  color: var(--primary);
  margin: 0;
}

.ai-header p {
  font-size: 12px;
  color: var(--on-surface-variant);
  margin: 0;
}

.ai-desc {
  font-size: 14px;
  color: var(--on-surface);
  margin-bottom: 16px;
}

.ai-features {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0;
  margin: 0;
}

.ai-features li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 14px;
  color: var(--on-surface);
  line-height: 1.5;
}

.ai-features li b {
  font-weight: 700;
}

/* Process steps */
.process-steps {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-left: 4px;
}

.process-steps::before {
  content: '';
  position: absolute;
  left: 11px;
  top: 16px;
  bottom: 16px;
  width: 2px;
  background: var(--outline-variant);
}

.process-step {
  display: flex;
  gap: 16px;
  position: relative;
  padding-bottom: 24px;
}

.process-step:last-child {
  padding-bottom: 0;
}

.step-dot {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--surface-container-highest);
  border: 1px solid var(--outline-variant);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  color: var(--outline);
  flex-shrink: 0;
  z-index: 1;
  transition: all 0.3s;
}

.step-dot.filled {
  background: var(--primary);
  border-color: var(--primary);
  color: white;
}

.process-step.active .step-dot {
  box-shadow: 0 0 0 4px var(--surface-container-lowest);
}

.step-info h4 {
  font-size: 14px;
  font-weight: 500;
  color: var(--outline);
  margin: 0 0 2px;
}

.process-step.active .step-info h4 {
  font-weight: 700;
  color: var(--on-surface);
}

.step-info p {
  font-size: 12px;
  color: var(--outline);
  margin: 0;
}

.process-step.active .step-info p {
  color: var(--on-surface-variant);
}

/* Tip card */
.tip-card {
  background: var(--surface-gray);
}

.tip-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--on-surface);
  margin-bottom: 8px;
}

.tip-card p {
  font-size: 13px;
  color: var(--on-surface-variant);
  line-height: 1.6;
  margin: 0;
}

/* Responsive */
@media (max-width: 1200px) {
  .page-layout {
    grid-template-columns: 1fr;
  }

  .info-sidebar {
    position: static;
  }
}

@media (max-width: 768px) {
  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
