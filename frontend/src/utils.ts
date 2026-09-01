export const extractError = (err: any): string => {
  const detail = err.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg || JSON.stringify(d)).join(', ');
  if (detail) return JSON.stringify(detail);
  return err.message || "An error occurred";
};
