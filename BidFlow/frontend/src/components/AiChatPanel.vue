<!-- AiChatPanel.vue - 项目 AI 助手对话面板（悬浮按钮触发，抽屉式） -->
<template>
  <div class="ai-chat">
    <!-- 悬浮按钮（可拖拽：pointerdown 开始，位移 <5px 视为点击打开抽屉） -->
    <button
      class="ai-fab"
      :class="{ active: visible, dragging: fabDragging }"
      :style="fabStyle"
      @pointerdown="onFabPointerDown"
      @pointermove="onFabPointerMove"
      @pointerup="onFabPointerUp"
      @pointercancel="onFabPointerUp"
      @keydown.enter="visible = true"
      aria-label="打开 AI 助手"
    >
      <span class="material-symbols-outlined">auto_awesome</span>
      <span class="fab-tooltip">AI 助手</span>
    </button>

    <!-- 聊天抽屉 -->
    <el-drawer
      v-model="visible"
      title="AI 项目助手"
      size="420px"
      :append-to-body="true"
      class="ai-chat-drawer"
    >
      <div class="chat-body">
        <!-- 消息区 -->
        <div ref="msgListRef" class="msg-list">
          <div v-if="!messages.length" class="chat-empty">
            <span class="material-symbols-outlined">chat_bubble_outline</span>
            <p>我是 BidFlow 项目助手，可以帮你：</p>
            <div class="quick-chips">
              <button v-for="q in QUICK_QUESTIONS" :key="q" class="quick-chip" @click="send(q)">{{ q }}</button>
            </div>
          </div>

          <div
            v-for="(m, i) in messages"
            :key="i"
            class="msg"
            :class="m.role"
          >
            <div class="bubble">
              <span v-if="m.toolCalls?.length" class="tool-tag">
                <span class="material-symbols-outlined">build</span>
                已调用：{{ m.toolCalls.join('、') }}
              </span>
              <span class="text">{{ m.content }}</span>
            </div>
          </div>

          <div v-if="sending" class="msg assistant">
            <div class="bubble typing">
              <span class="dot" /><span class="dot" /><span class="dot" />
            </div>
          </div>
        </div>

        <!-- 输入区 -->
        <div class="chat-input">
          <el-input
            v-model="draft"
            type="textarea"
            :rows="2"
            resize="none"
            placeholder="问项目进展、风险、未匹配项…"
            @keydown.enter.exact="onEnter"
          />
          <el-button type="primary" :loading="sending" :disabled="!draft.trim()" @click="send()">
            <template #icon><span class="material-symbols-outlined">send</span></template>
            发送
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { chatProject } from '@/api/chat'
import { parseResponse } from '@/utils/api'

const props = defineProps({
  projectId: { type: [Number, String], required: true }
})

const visible = ref(false)
const draft = ref('')
const sending = ref(false)
const messages = ref([])
const msgListRef = ref(null)

// ---- 悬浮按钮拖拽（避免与右下角"保存草案"等操作重叠）----
const FAB_POS_KEY = 'bidflow_ai_fab_pos'
const fabPos = ref(null) // {left, top} 用户拖拽后的位置；null = 默认右下角
const fabDragging = ref(false)
const dragStart = ref(null) // {x, y, left, top}
let dragMoved = false // 是否发生了位移（区分点击/拖拽）

const fabStyle = computed(() => {
  if (fabPos.value) {
    return { left: `${fabPos.value.left}px`, top: `${fabPos.value.top}px` }
  }
  return { right: '24px', bottom: '24px' }
})

function onFabPointerDown(e) {
  if (e.button !== 0 && e.pointerType === 'mouse') return
  const rect = e.currentTarget.getBoundingClientRect()
  dragStart.value = { x: e.clientX, y: e.clientY, left: rect.left, top: rect.top }
  dragMoved = false
  fabDragging.value = true
}

function onFabPointerMove(e) {
  if (!fabDragging.value || !dragStart.value) return
  const dx = e.clientX - dragStart.value.x
  const dy = e.clientY - dragStart.value.y
  if (Math.abs(dx) < 5 && Math.abs(dy) < 5) return // 尚未拖出点击阈值
  dragMoved = true
  const btnW = e.currentTarget.offsetWidth || 56
  const btnH = e.currentTarget.offsetHeight || 56
  const maxLeft = Math.max(8, window.innerWidth - btnW - 8)
  const maxTop = Math.max(8, window.innerHeight - btnH - 8)
  const left = Math.min(Math.max(8, dragStart.value.left + dx), maxLeft)
  const top = Math.min(Math.max(8, dragStart.value.top + dy), maxTop)
  fabPos.value = { left, top }
}

function onFabPointerUp() {
  if (!fabDragging.value) return
  fabDragging.value = false
  dragStart.value = null
  if (dragMoved) {
    dragMoved = false
    // 拖拽结束：记住位置，下次进入仍在此处
    try {
      if (fabPos.value) localStorage.setItem(FAB_POS_KEY, JSON.stringify(fabPos.value))
    } catch { /* localStorage 不可用时忽略 */ }
    return // 拖拽不算点击，不打开抽屉
  }
  visible.value = true // 纯点击 → 打开抽屉
}

onMounted(() => {
  try {
    const raw = localStorage.getItem(FAB_POS_KEY)
    if (raw) {
      const p = JSON.parse(raw)
      if (typeof p?.left === 'number' && typeof p?.top === 'number') fabPos.value = p
    }
  } catch { /* 忽略损坏数据 */ }
})

const QUICK_QUESTIONS = [
  '项目整体进展如何？',
  '有哪些未匹配到资料的需求？',
  '当前有什么合规风险？',
  '帮我重新核查合规',
  '给我一份风险修复建议',
]

async function scrollToBottom() {
  await nextTick()
  if (msgListRef.value) msgListRef.value.scrollTop = msgListRef.value.scrollHeight
}

async function send(text) {
  const content = (text ?? draft.value ?? '').trim()
  if (!content || sending.value) return
  draft.value = ''
  messages.value.push({ role: 'user', content })
  sending.value = true
  scrollToBottom()
  try {
    const res = await chatProject(props.projectId, content)
    const data = parseResponse(res, {})
    messages.value.push({
      role: 'assistant',
      content: data?.reply || '（无回复）',
      toolCalls: data?.tool_calls_used || [],
    })
    // 工具可能改了数据，通知父组件刷新
    if ((data?.tool_calls_used || []).length) {
      emit('tools-executed')
    }
  } catch (e) {
    ElMessage.error(e?.message || 'AI 助手请求失败')
    messages.value.push({ role: 'assistant', content: '抱歉，AI 服务暂时不可用，请稍后再试。' })
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

// M10：Enter 发送需避开中文输入法组合态（拼音选词确认时 isComposing=true，不应发送）
function onEnter(e) {
  if (e.isComposing || e.keyCode === 229) return
  e.preventDefault()
  send()
}

const emit = defineEmits(['tools-executed'])

watch(visible, (v) => { if (v) scrollToBottom() })
</script>

<style scoped>
.ai-fab {
  position: fixed;
  z-index: 3000;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: none;
  cursor: grab;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  background: linear-gradient(135deg, #6a5cff, #8b5cf6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 24px rgba(107, 92, 255, 0.35);
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.3s;
}
.ai-fab:hover, .ai-fab.active {
  transform: scale(1.08) rotate(8deg);
  box-shadow: 0 12px 32px rgba(107, 92, 255, 0.5);
}
.ai-fab.dragging {
  cursor: grabbing;
  transform: scale(1.08);
  box-shadow: 0 16px 40px rgba(107, 92, 255, 0.55);
}
.ai-fab .material-symbols-outlined { font-size: 26px; }
.fab-tooltip {
  position: absolute;
  right: 64px;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(0,0,0,0.75);
  color: #fff;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
}
.ai-fab:hover .fab-tooltip { opacity: 1; }

.chat-body { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.msg-list { flex: 1; overflow-y: auto; padding: 4px 2px 16px; display: flex; flex-direction: column; gap: 12px; }

.chat-empty { text-align: center; color: #999; padding: 32px 8px; }
.chat-empty .material-symbols-outlined { font-size: 40px; opacity: 0.5; }
.chat-empty p { font-size: 13px; margin: 8px 0 16px; }
.quick-chips { display: flex; flex-direction: column; gap: 8px; align-items: stretch; padding: 0 12px; }
.quick-chip {
  border: 1px solid #e0e0e0;
  background: #fafafa;
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 13px;
  cursor: pointer;
  color: #555;
  transition: all 0.2s;
}
.quick-chip:hover { background: #eef0ff; border-color: #6a5cff; color: #6a5cff; }

.msg { display: flex; }
.msg.user { justify-content: flex-end; }
.bubble {
  max-width: 86%;
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg.user .bubble { background: linear-gradient(135deg, #6a5cff, #8b5cf6); color: #fff; border-bottom-right-radius: 4px; }
.msg.assistant .bubble { background: #f1f2f7; color: #333; border-bottom-left-radius: 4px; }
.tool-tag {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; color: #6a5cff; background: rgba(106,92,255,0.1);
  padding: 2px 8px; border-radius: 999px; margin-bottom: 6px;
}
.tool-tag .material-symbols-outlined { font-size: 13px; }
.msg.user .bubble .text { display: block; }

.typing { display: flex; gap: 4px; align-items: center; padding: 14px; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: #999; animation: blink 1.2s infinite; }
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink { 0%, 80%, 100% { opacity: 0.3; } 40% { opacity: 1; } }

.chat-input { display: flex; gap: 8px; align-items: flex-end; border-top: 1px solid #eee; padding-top: 12px; }
.chat-input .el-input { flex: 1; }
.chat-input .el-button { height: 56px; }
</style>
