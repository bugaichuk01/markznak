import axios from "axios";

const apiBase =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || "/api/v1";

const apiClient = axios.create({
  baseURL: apiBase.replace(/\/+$/, ""),
  timeout: 15000,
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error("API request failed:", error);
    return Promise.reject(error);
  },
);

export default apiClient;
