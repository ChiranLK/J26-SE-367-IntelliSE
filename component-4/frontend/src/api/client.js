import axios from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export const apiClient = axios.create({
  baseURL,
  timeout: 15000,
  headers: {
    'Accept': 'application/json',
  },
});

// Response interceptor for consistent error extraction
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    let message = 'An unexpected error occurred.';
    let errorCode = 'UNKNOWN_ERROR';
    let details = null;

    if (error.response) {
      // Backend returned an error response
      const data = error.response.data;
      if (data && data.error) {
        errorCode = data.error.code || `HTTP_${error.response.status}`;
        message = data.error.message || message;
        details = data.error.details || null;
      } else if (data && data.detail) {
        // Standard FastAPI detail (if not caught by custom handler)
        message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
        errorCode = `HTTP_${error.response.status}`;
      } else {
        message = error.response.statusText || `Request failed with status ${error.response.status}`;
        errorCode = `HTTP_${error.response.status}`;
      }
    } else if (error.request) {
      // Request was made but no response received (backend offline)
      errorCode = 'BACKEND_OFFLINE';
      message = 'Unable to connect to Component 4 backend. Please ensure the FastAPI server is running at ' + baseURL;
    } else {
      message = error.message;
    }

    const enhancedError = new Error(message);
    enhancedError.errorCode = errorCode;
    enhancedError.status = error.response ? error.response.status : 0;
    enhancedError.details = details;
    enhancedError.rawError = error;

    return Promise.reject(enhancedError);
  }
);

export default apiClient;
