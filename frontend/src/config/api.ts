const isDev = import.meta.env.DEV;
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://api.stat-vision.xyz';

export const getApiUrl = (endpoint: string): string => {
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;

  if (isDev) {
    return cleanEndpoint;
  }

  const cleanBaseUrl = API_BASE_URL.endsWith('/') ? API_BASE_URL.slice(0, -1) : API_BASE_URL;
  return `${cleanBaseUrl}${cleanEndpoint}`;
};
