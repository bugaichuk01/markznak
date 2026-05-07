import axios from "axios";

const apiClient = axios.create({
  baseURL: "/api/v1",
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
