const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const TOKEN_KEY = "hrmsai_access_token";

export const apiEnabled = Boolean(API_URL);

export const apiRequest = async (path, options = {}) => {
  if (!apiEnabled) throw new Error("API mode is not configured");
  const token = localStorage.getItem(TOKEN_KEY);
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? {Authorization: `Bearer ${token}`} : {}),
      ...(options.headers || {})
    }
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
};

export const apiLogin = async (email, password) => {
  const result = await apiRequest("/auth/login", {
    method: "POST",
    body: JSON.stringify({email, password})
  });
  localStorage.setItem(TOKEN_KEY, result.access_token);
  return result;
};

export const apiRegister = async ({email, password, name, workspace, full_name}) => {
  const result = await apiRequest("/auth/register", {
    method: "POST",
    body: JSON.stringify({email, password, name, workspace, full_name})
  });
  localStorage.setItem(TOKEN_KEY, result.access_token);
  return result;
};

export const apiLogout = () => localStorage.removeItem(TOKEN_KEY);

export const apiListEmployees = () => apiRequest("/employees");
export const apiListMessages = () => apiRequest("/messages");
export const apiSendMessage = (text) => apiRequest("/messages", {method: "POST", body: JSON.stringify({text})});
export const apiUploadResume = async (file) => {
  const token = localStorage.getItem(TOKEN_KEY);
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_URL}/resumes`, {method: "POST", headers: token ? {Authorization: `Bearer ${token}`} : {}, body});
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || `Resume upload failed (${response.status})`);
  return result;
};
