"use client";

import dynamic from "next/dynamic";

const VoiceAgentWrapper = dynamic(() => import("./VoiceAgentWrapper"), {
  ssr: false,
  loading: () => null,
});

export default function DeferredVoiceAgent() {
  return <VoiceAgentWrapper />;
}
