/// 日期工具：服务端 ISO 时间字符串解析（M 前端时区 bug 修复）。
///
/// 根因：后端 datetime.utcnow() 序列化为 ISO 时无时区后缀（不带 Z），
///       JS Date 按本地时区（UTC+8）解析会偏移 8 小时。
///
/// 解法：统一把无 tz 后缀的字符串视为 UTC 解析，加 'Z' 后再 new Date。
export function parseServerDate(input) {
  if (!input) return null
  const s = String(input)
  // 已有 Z / +HH:MM / +HHMM 时区后缀 → 直接解析；否则补 'Z' 按 UTC 解析
  const hasTz = /[Zz]$|[+-]\d{2}:?\d{2}$/.test(s)
  const d = new Date(hasTz ? s : s + 'Z')
  return isNaN(d.getTime()) ? null : d
}