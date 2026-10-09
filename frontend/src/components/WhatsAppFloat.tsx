"use client";

import { usePathname } from "next/navigation";
import { WHATSAPP_CONTACT_URL } from "@/lib/contact";
import styles from "./WhatsAppFloat.module.css";

export default function WhatsAppFloat() {
  const pathname = usePathname();
  if (pathname !== "/") return null;
  return (
    <a
      className={styles.contact}
      href={WHATSAPP_CONTACT_URL}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Chat with Agent 0 on WhatsApp"
      title="Chat with Agent 0 on WhatsApp"
    >
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12.04 2a9.91 9.91 0 0 0-8.48 15.04L2.2 21.8l4.91-1.29A9.92 9.92 0 1 0 12.04 2Zm0 18.02a8.08 8.08 0 0 1-4.12-1.13l-.3-.18-2.92.77.78-2.84-.2-.31a8.1 8.1 0 1 1 6.76 3.69Zm4.44-6.07c-.24-.12-1.43-.71-1.65-.79-.22-.08-.38-.12-.54.12-.16.24-.62.79-.76.95-.14.16-.28.18-.52.06-.24-.12-1.01-.37-1.92-1.18-.71-.63-1.19-1.42-1.33-1.66-.14-.24-.01-.37.1-.49.11-.1.24-.28.36-.42.12-.14.16-.24.24-.4.08-.16.04-.3-.02-.42-.06-.12-.54-1.3-.74-1.78-.19-.46-.39-.4-.54-.41h-.46c-.16 0-.42.06-.64.3-.22.24-.84.82-.84 2s.86 2.32.98 2.48c.12.16 1.69 2.58 4.1 3.62.57.25 1.02.4 1.37.51.58.18 1.1.16 1.51.1.46-.07 1.43-.58 1.63-1.14.2-.56.2-1.04.14-1.14-.06-.1-.22-.16-.46-.28Z" />
      </svg>
      <span>WhatsApp us</span>
    </a>
  );
}
