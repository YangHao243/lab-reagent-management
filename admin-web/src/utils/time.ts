const BEIJING_TIME_ZONE = "Asia/Shanghai";

function pad(value: number) {
  return String(value).padStart(2, "0");
}

function formatParts(year: number, month: number, day: number, hour: number, minute: number, second: number) {
  return `${year}/${month}/${day} ${pad(hour)}:${pad(minute)}:${pad(second)}`;
}

function formatDateWithIntl(date: Date) {
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: BEIJING_TIME_ZONE,
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const valueMap = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${valueMap.year}/${valueMap.month}/${valueMap.day} ${valueMap.hour}:${valueMap.minute}:${valueMap.second}`;
}

export function formatBeijingTime(value?: string | null) {
  if (!value) return "-";

  const text = String(value).trim();
  if (!text) return "-";

  // 后端 DateTime 字段当前返回 naive 北京时间；这类字符串不能交给 Date 按浏览器时区转换。
  const naiveMatch = text.match(
    /^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T\s](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?(?:\.\d+)?)?$/,
  );
  if (naiveMatch) {
    const [, year, month, day, hour = "0", minute = "0", second = "0"] = naiveMatch;
    return formatParts(
      Number(year),
      Number(month),
      Number(day),
      Number(hour),
      Number(minute),
      Number(second),
    );
  }

  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  return formatDateWithIntl(date);
}
