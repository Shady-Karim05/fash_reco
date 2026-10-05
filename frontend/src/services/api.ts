import axios, { AxiosError } from 'axios';

// Get base URL from Vite environment variable; do not hardcode localhost
const rawBaseUrl = import.meta.env.VITE_API_BASE_URL;

// In local development, forward via Vite's proxy to avoid browser CORS blocks
const isLocalDev =
  import.meta.env.DEV &&
  Boolean(rawBaseUrl && (rawBaseUrl.includes('localhost:8000') || rawBaseUrl.includes('127.0.0.1:8000')));

export const API_BASE_URL = isLocalDev ? '' : (rawBaseUrl ? rawBaseUrl.replace(/\/+$/, '') : '');

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

export interface ApiErrorMessage {
  title: string;
  detail: string;
  statusCode?: number;
}

/**
 * Normalizes Axios or network errors into clean, user-friendly messages.
 * Never leaks raw stack traces or internal backend errors to users.
 */
export function formatApiError(error: unknown): ApiErrorMessage {
  if (axios.isAxiosError(error)) {
    const axiosErr = error as AxiosError<{ message?: string; detail?: string | Array<{ msg: string }> }>;

    if (!axiosErr.response) {
      if (axiosErr.code === 'ECONNABORTED') {
        return {
          title: 'Request Timed Out',
          detail: 'The search server took too long to respond. Please try again.',
        };
      }
      return {
        title: 'Service Unavailable',
        detail: 'Unable to connect to the recommendation service. Please verify the backend service is running on port 8000.',
      };
    }

    const status = axiosErr.response.status;
    const data = axiosErr.response.data;

    if (status === 422) {
      let detailMsg = 'Please verify your search query parameters.';
      if (Array.isArray(data?.detail) && data.detail.length > 0) {
        detailMsg = data.detail.map((d) => d.msg).join(', ');
      }
      return {
        title: 'Invalid Request',
        detail: detailMsg,
        statusCode: status,
      };
    }

    if (status === 404) {
      return {
        title: 'Not Found',
        detail: data?.message || 'The requested resource or product could not be found.',
        statusCode: status,
      };
    }

    if (status >= 500) {
      return {
        title: 'Search Service Error',
        detail: 'The recommendation engine encountered a temporary problem. Please try again in a moment.',
        statusCode: status,
      };
    }

    return {
      title: 'Request Failed',
      detail: (typeof data?.detail === 'string' ? data.detail : data?.message) || 'An unexpected response was received.',
      statusCode: status,
    };
  }

  return {
    title: 'Unexpected Error',
    detail: 'An unexpected application error occurred. Please refresh or try again.',
  };
}
