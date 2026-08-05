// API response parsing utilities
// Backend responses may come as data directly or wrapped in { data: ... }

/**
 * Safely extract payload from API response.
 * Handles both: direct data and { data: payload } formats.
 * @param {*} res - Raw axios response
 * @param {*} fallback - Value to return if data is undefined
 * @returns {*} Extracted payload
 */
export function parseResponse(res, fallback = null) {
  if (res === undefined || res === null) return fallback
  const data = res.data !== undefined ? res.data : res
  return data !== undefined && data !== null ? data : fallback
}

/**
 * Safely extract array payload from API response.
 * @param {*} res - Raw axios response
 * @returns {Array} Extracted array or empty array
 */
export function parseArray(res) {
  const data = parseResponse(res, [])
  return Array.isArray(data) ? data : []
}