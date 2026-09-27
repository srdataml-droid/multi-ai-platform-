"use client";

import { api, post } from "./api";

export type AlertStatus = {
  public_key: string | null;
  channels: { push_available: boolean; push_devices: number; email: boolean; sms: boolean };
  alerts_off: boolean;
  this_user_subscribed: boolean;
  can_subscribe: boolean;
};

export function pushSupported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function keyBytes(b64url: string): Uint8Array<ArrayBuffer> {
  const pad = "=".repeat((4 - (b64url.length % 4)) % 4);
  const raw = atob((b64url + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

// Ask this browser for permission and register it for staff alerts.
export async function turnOnAlerts(publicKey: string): Promise<AlertStatus> {
  if (!pushSupported()) throw new Error("This browser cannot receive alerts. On iPhone, add the dashboard to your Home Screen first.");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notifications are blocked for this site. Allow them in the browser settings.");
  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  const sub = (await reg.pushManager.getSubscription()) ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(publicKey) }));
  return post<AlertStatus>("/alerts/subscriptions", sub.toJSON());
}

export async function turnOffAlerts(): Promise<AlertStatus> {
  const reg = await navigator.serviceWorker.getRegistration("/sw.js");
  const sub = reg ? await reg.pushManager.getSubscription() : null;
  if (sub) {
    await post("/alerts/subscriptions/remove", { endpoint: sub.endpoint });
    await sub.unsubscribe();
  }
  return api<AlertStatus>("/alerts");
}
