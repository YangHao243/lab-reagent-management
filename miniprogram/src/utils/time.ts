function pad2(value: number) {
  return String(value).padStart(2, "0");
}

function formatDateParts(date: Date) {
  return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()} ${pad2(
    date.getHours(),
  )}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

// 后端无时区的时间字符串按北京时间本地时间处理，避免 10:00 被错误换算成 02:00。
export function formatBeijingTime(value?: string | null) {
  if (!value) {
    return "-";
  }

  const text = String(value).trim();
  if (!text) {
    return "-";
  }

  const hasTimezone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(text);
  if (!hasTimezone) {
    const normalized = text.replace("T", " ").replace(/\.\d+$/, "");
    const match = normalized.match(
      /^(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/,
    );
    if (match) {
      const [, year, month, day, hour = "0", minute = "0", second = "0"] = match;
      return `${Number(year)}/${Number(month)}/${Number(day)} ${pad2(Number(hour))}:${pad2(
        Number(minute),
      )}:${pad2(Number(second))}`;
    }
  }

  const date = new Date(text);
  if (Number.isNaN(date.getTime())) {
    return text;
  }

  // 微信小程序环境通常跟随设备时区；这里明确按 Asia/Shanghai 取值。
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(date);

  const get = (type: string) => parts.find((part) => part.type === type)?.value || "0";
  return `${Number(get("year"))}/${Number(get("month"))}/${Number(get("day"))} ${pad2(
    Number(get("hour")),
  )}:${pad2(Number(get("minute")))}:${pad2(Number(get("second")))}`;
}

export function formatShortDate(value?: string | null) {
  const full = formatBeijingTime(value);
  return full === "-" ? full : full.split(" ")[0];
}

export function formatLocalNowDate() {
  return formatDateParts(new Date()).split(" ")[0];
}
