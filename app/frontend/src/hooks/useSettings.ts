import { useState, useCallback } from "react";

export interface LogoPreset {
  label: string;
  url: string;
}

export const LOGO_PRESETS: LogoPreset[] = [
  {
    label: "Cloudera",
    url: "https://external-content.duckduckgo.com/iu/?u=https%3A%2F%2Fml.globenewswire.com%2FResource%2FDownload%2F24cdff2f-7c95-4f21-aebb-25c4628d94e7&f=1&nofb=1&ipt=f7d3c9281a9b281cdee78da46582ea05897737b593471354b6734f427d8ec4ac",
  },
];

const STORAGE_KEY = "dq-logo-url";
const DEFAULT_LOGO = LOGO_PRESETS[0].url;

export function useSettings() {
  const [logoUrl, setLogoUrlState] = useState<string>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) || DEFAULT_LOGO;
    } catch {
      return DEFAULT_LOGO;
    }
  });

  const setLogoUrl = useCallback((url: string) => {
    setLogoUrlState(url);
    try {
      localStorage.setItem(STORAGE_KEY, url);
    } catch {
      // localStorage unavailable
    }
  }, []);

  return { logoUrl, setLogoUrl };
}
