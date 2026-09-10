"use client";
import { useEffect, useRef, useState } from "react";

interface Props {
  onTranscript: (text: string) => void;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Recognition = any;

export default function MicButton({ onTranscript }: Props) {
  const [listening, setListening] = useState(false);
  const [supported, setSupported] = useState(true);
  const recognitionRef = useRef<Recognition>(null);

  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const w = window as any;
    const SpeechRecognition = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setSupported(false);
      return;
    }
    const rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = false;
    rec.lang = "en-US";
    rec.onresult = (e: Recognition) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) onTranscript(e.results[i][0].transcript.trim());
      }
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recognitionRef.current = rec;
    return () => rec.stop();
  }, [onTranscript]);

  function toggle() {
    const rec = recognitionRef.current;
    if (!rec) return;
    if (listening) {
      rec.stop();
      setListening(false);
    } else {
      rec.start();
      setListening(true);
    }
  }

  if (!supported) {
    return <span className="text-xs text-stone-400">Voice input needs Chrome or Edge.</span>;
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className={`flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
        listening
          ? "bg-red-50 border-red-300 text-red-700"
          : "bg-white border-stone-200 text-stone-600 hover:border-stone-400"
      }`}
    >
      <span className={`w-2 h-2 rounded-full ${listening ? "bg-red-500 animate-pulse" : "bg-stone-400"}`} />
      {listening ? "Listening... click to stop" : "Speak your answer"}
    </button>
  );
}
