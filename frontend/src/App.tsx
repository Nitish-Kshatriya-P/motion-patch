import { useState, useEffect, useCallback, useRef } from 'react';
import type { DragEvent } from 'react';
import axios from 'axios';
import SessionSidebar, { formatSessionTitle, type SessionSummary } from './components/SessionSidebar';
import ChatStream, { type ChatMessage, type ProposedPlanData } from './components/ChatStream';
import MultimodalPromptBar from './components/MultimodalPromptBar';
import Viewport3D from './components/Viewport3D';
import type { DiagnosticCardProps, FindingItem } from './components/DiagnosticCard';
import type { DynamicAgent } from './components/DynamicAgentRosterCard';
import WhiteBoxCodeDrawer from './components/WhiteBoxCodeDrawer';
import type { ComparisonMode } from './components/ComparisonControls';
import MotionPatchLogo from './components/MotionPatchLogo';
import KeyboardShortcutsModal from './components/KeyboardShortcutsModal';
import { Keyboard, PanelLeft, Box, Bot, Columns2 } from 'lucide-react';
import { API_BASE_URL } from './config';

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const base64String = (reader.result as string).split(',')[1] || '';
      resolve(base64String);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function mapFindingToInterval(f: any): FindingItem {
  const frameStart = Number(f.frame_start ?? 0);
  const frameEnd = Number(f.frame_end ?? frameStart);
  const peakFrame = f.peak_frame != null ? Number(f.peak_frame) : frameStart;
  const playbackStart = f.playback_frame_start != null ? Number(f.playback_frame_start) : Math.max(0, frameStart - 15);
  const playbackEnd = f.playback_frame_end != null ? Number(f.playback_frame_end) : frameEnd + 15;
  const jointName = f.affected_joint || f.joint || 'Unknown';

  return {
    finding_id: f.finding_id,
    joint: jointName,
    affected_joint: jointName,
    frame_start: frameStart,
    frame_end: frameEnd,
    display_frame_start: f.display_frame_start != null ? Number(f.display_frame_start) : frameStart + 1,
    display_frame_end: f.display_frame_end != null ? Number(f.display_frame_end) : frameEnd + 1,
    peak_frame: peakFrame,
    display_peak_frame: f.display_peak_frame != null ? Number(f.display_peak_frame) : peakFrame + 1,
    playback_frame_start: playbackStart,
    playback_frame_end: playbackEnd,
    display_playback_frame_start: f.display_playback_frame_start != null ? Number(f.display_playback_frame_start) : playbackStart + 1,
    display_playback_frame_end: f.display_playback_frame_end != null ? Number(f.display_playback_frame_end) : playbackEnd + 1,
    time_start: Number(f.time_start ?? 0),
    time_end: Number(f.time_end ?? 0),
    anomaly_type: f.anomaly_type,
    severity: f.severity,
    confidence: f.confidence != null ? Number(f.confidence) : undefined,
    verdict: f.verdict || undefined,
    evidence: f.evidence || undefined,
    explanation: f.explanation || '',
  };
}

export default function App() {
  const [comparisonMode, setComparisonMode] = useState<ComparisonMode>('repaired');
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activeBvhId, setActiveBvhId] = useState<string | null>(null);
  const [originalBvhId, setOriginalBvhId] = useState<string | null>(null);
  const [repairedBvhId, setRepairedBvhId] = useState<string | null>(null);
  const [activeFilename, setActiveFilename] = useState<string | null>(null);
  const [activePlanId, setActivePlanId] = useState<string | null>(null);
  const [activeApprovalId, setActiveApprovalId] = useState<string | null>(null);
  const [isCodeDrawerOpen, setIsCodeDrawerOpen] = useState(false);
  const [currentScriptCode, setCurrentScriptCode] = useState<string>('');
  const [isExecutingScript, setIsExecutingScript] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('motionpatch_sidebar_open');
      return saved !== null ? saved === 'true' : true;
    } catch {
      return true;
    }
  });
  const [sessionUploadCount, setSessionUploadCount] = useState<number>(0);
  const [isUploading, setIsUploading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isLoadingSessions, setIsLoadingSessions] = useState(true);
  const [isDragOverWindow, setIsDragOverWindow] = useState(false);
  const [stagedFile, setStagedFile] = useState<File | null>(null);
  const [activeBrokenIntervals, setActiveBrokenIntervals] = useState<FindingItem[]>([]);
  const [activeTotalFrames, setActiveTotalFrames] = useState<number>(0);
  const [activeFps, setActiveFps] = useState<number>(30);
  const [selectedFinding, setSelectedFinding] = useState<{
    findingId?: string;
    frameStart: number;
    joint?: string;
    timestamp?: number;
  } | null>(null);
  const [mobileViewMode, setMobileViewMode] = useState<'viewport' | 'chat' | 'split'>('viewport');
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);
  const [sessionFetchError, setSessionFetchError] = useState<string | null>(null);
  const sessionSelectReqIdRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!activeSessionId || messages.length === 0) return;
    const hasForeignSession = messages.some(
      (m) => m.sessionId && m.sessionId !== activeSessionId
    );
    if (hasForeignSession) return;

    try {
      localStorage.setItem(`mocap_chat_history_${activeSessionId}`, JSON.stringify(messages));
    } catch {}

    const timer = setTimeout(() => {
      try {
        const p = axios.post(`${API_BASE_URL}/sessions/${activeSessionId}/messages`, { messages });
        if (p && typeof p.catch === 'function') {
          p.catch(() => {});
        }
      } catch {}
    }, 400);

    return () => clearTimeout(timer);
  }, [messages, activeSessionId]);

  const handleToggleSidebar = useCallback(() => {
    setIsSidebarOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('motionpatch_sidebar_open', String(next));
      } catch {}
      return next;
    });
  }, []);

  const fetchSessions = useCallback(async () => {
    setIsLoadingSessions(true);
    setSessionFetchError(null);
    try {
      const res = await axios.get(`${API_BASE_URL}/sessions`);
      setSessions(res.data);
    } catch (err: any) {
      console.error(err);
      const detail = err?.response?.data?.detail || err.message || 'Failed to load threads';
      setSessionFetchError(detail);
    } finally {
      setIsLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleNewSession = useCallback(() => {
    setActiveSessionId(null);
    setActiveBvhId(null);
    setOriginalBvhId(null);
    setRepairedBvhId(null);
    setActiveFilename(null);
    setActivePlanId(null);
    setActiveApprovalId(null);
    setCurrentScriptCode('');
    setIsCodeDrawerOpen(false);
    setActiveBrokenIntervals([]);
    setActiveTotalFrames(0);
    setActiveFps(30);
    setSelectedFinding(null);
    setMessages([]);
    setIsUploading(false);
    setIsGenerating(false);
    setStagedFile(null);
    setSessionUploadCount(0);
  }, []);

  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      const activeTag = (document.activeElement?.tagName || '').toLowerCase();
      if (activeTag === 'input' || activeTag === 'textarea' || (document.activeElement as HTMLElement)?.isContentEditable) {
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        handleToggleSidebar();
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        handleNewSession();
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'i') {
        e.preventDefault();
        setIsCodeDrawerOpen((prev) => !prev);
      } else if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault();
        setIsShortcutsOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => {
      window.removeEventListener('keydown', handleGlobalKeyDown);
    };
  }, [handleNewSession, handleToggleSidebar]);

  const handleSelectSession = async (session: SessionSummary) => {
    sessionSelectReqIdRef.current += 1;
    const currentReqId = sessionSelectReqIdRef.current;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const ac = new AbortController();
    abortControllerRef.current = ac;

    setActiveSessionId(session.session_id);
    const sessionTitle = formatSessionTitle(session);
    setActiveFilename(sessionTitle);
    setActivePlanId(session.plan_id || null);
    setActiveApprovalId(session.approval_id || null);

    try {
      const filesRes = await axios.get(`${API_BASE_URL}/sessions/${session.session_id}/files`, {
        signal: ac.signal,
      });
      if (currentReqId === sessionSelectReqIdRef.current) {
        if (typeof filesRes.data?.count === 'number') {
          setSessionUploadCount(filesRes.data.count);
        } else {
          setSessionUploadCount(1);
        }
      }
    } catch {
      if (currentReqId === sessionSelectReqIdRef.current) {
        setSessionUploadCount(1);
      }
    }

    if (currentReqId !== sessionSelectReqIdRef.current) return;

    const origId = session.original_asset_id || session.asset_id;
    const repId = session.repaired_asset_id && session.repaired_asset_id !== origId ? session.repaired_asset_id : null;

    setActiveBvhId(session.asset_id);
    setRepairedBvhId(repId);
    setOriginalBvhId(origId);

    try {
      const res = await axios.get(`${API_BASE_URL}/analyses/${session.analysis_id}/summary`, {
        signal: ac.signal,
      });
      if (currentReqId !== sessionSelectReqIdRef.current) return;
      const summaryData = res.data;

      if (summaryData.asset_id) {
        setOriginalBvhId(summaryData.asset_id);
      }

      const isApproved = session.lifecycle_state === 'APPROVED' && Boolean(session.approval_id);
      const rawIntervals = summaryData.findings || summaryData.frame_intervals || [];
      const intervals: FindingItem[] = rawIntervals.map(mapFindingToInterval);
      const brokenJoints = summaryData.broken_joints && summaryData.broken_joints.length > 0
        ? summaryData.broken_joints
        : Array.from(new Set(intervals.map((f) => f.affected_joint || f.joint))).filter(Boolean);

      const cardProps: DiagnosticCardProps = {
        analysisId: summaryData.analysis_id,
        sessionId: session.session_id,
        status: summaryData.status,
        summary: summaryData.summary,
        brokenJoints,
        frameIntervals: intervals,
        durationSeconds: summaryData.duration_seconds || 0,
        frameCount: summaryData.frame_count || 0,
        fps: summaryData.fps || 30,
        isApproved,
        approvalId: session.approval_id || undefined,
      };

      setActiveBrokenIntervals(intervals);
      setActiveTotalFrames(summaryData.frame_count || 0);
      setActiveFps(summaryData.fps || 30);
      setSelectedFinding(null);

      let loadedMessages: ChatMessage[] = [];
      try {
        const cached = localStorage.getItem(`mocap_chat_history_${session.session_id}`);
        if (cached) {
          const parsed = JSON.parse(cached);
          if (Array.isArray(parsed) && parsed.length > 0) {
            loadedMessages = parsed;
          }
        }
      } catch {}

      try {
        const msgRes = await axios.get(`${API_BASE_URL}/sessions/${session.session_id}/messages`, {
          signal: ac.signal,
        });
        if (msgRes.data && Array.isArray(msgRes.data.messages) && msgRes.data.messages.length > 0) {
          loadedMessages = msgRes.data.messages;
        }
      } catch {}

      if (currentReqId !== sessionSelectReqIdRef.current) return;

      if (loadedMessages.length === 0) {
        loadedMessages = [
          {
            id: `load-${session.session_id}-user`,
            sender: 'user',
            timestamp: session.created_at,
            text: `Opened session: ${sessionTitle}`,
            sessionId: session.session_id,
          },
          {
            id: `load-${session.session_id}-assistant`,
            sender: 'assistant',
            timestamp: session.created_at,
            text: `Retrieved kinematic diagnostic record for asset ${sessionTitle}.`,
            diagnosticData: cardProps,
            sessionId: session.session_id,
            isApproved,
            approvalId: session.approval_id || undefined,
          },
        ];
        try {
          const p = axios.post(`${API_BASE_URL}/sessions/${session.session_id}/messages`, { messages: loadedMessages });
          if (p && typeof p.catch === 'function') {
            p.catch(() => {});
          }
        } catch {}
      }

      setMessages(loadedMessages);
      try {
        localStorage.setItem(`mocap_chat_history_${session.session_id}`, JSON.stringify(loadedMessages));
      } catch {}
    } catch (err: any) {
      if (axios.isCancel(err) || currentReqId !== sessionSelectReqIdRef.current) return;
      console.error(err);
      setMessages([
        {
          id: `load-error-${Date.now()}`,
          sender: 'assistant',
          timestamp: new Date().toISOString(),
          text: `Loaded session ${sessionTitle}, but could not retrieve diagnostic narrative.`,
        },
      ]);
    }
  };

  const handleFileUpload = async (file: File, userPrompt?: string) => {
    if (!file.name.toLowerCase().endsWith('.bvh')) {
      return;
    }

    if (sessionUploadCount >= 5) {
      setStagedFile(null);
      const limitMsg: ChatMessage = {
        id: `limit-${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toISOString(),
        text: 'Upload limit reached: A maximum of 5 files can be uploaded in a single chat session. Start a new thread (Cmd+N) to analyze more files.',
      };
      setMessages((prev) => [...prev, limitMsg]);
      return;
    }

    setStagedFile(null);
    const userMsgId = `user-${Date.now()}`;
    const userMsg: ChatMessage = {
      id: userMsgId,
      sender: 'user',
      timestamp: new Date().toISOString(),
      text: userPrompt
        ? `${userPrompt}\n(Attached file: ${file.name})`
        : `Uploaded ${file.name} (${(file.size / 1024).toFixed(1)} KB)`,
      sessionId: activeSessionId || undefined,
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsUploading(true);

    const formData = new FormData();
    formData.append('file', file);
    if (userPrompt) {
      formData.append('prompt', userPrompt);
    }
    if (activeSessionId) {
      formData.append('session_id', activeSessionId);
    }

    try {
      const res = await axios.post(`${API_BASE_URL}/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      const data = res.data;
      setActiveBvhId(data.id);
      setOriginalBvhId(data.id);
      setRepairedBvhId(null);
      setActiveSessionId(data.session_id);
      setActiveFilename(file.name);
      if (typeof data.uploaded_files_count === 'number') {
        setSessionUploadCount(data.uploaded_files_count);
      } else {
        setSessionUploadCount((prev) => prev + 1);
      }

      const findings = data.findings || [];
      const frameIntervals: FindingItem[] = findings.map(mapFindingToInterval);
      const brokenJoints = Array.from(new Set(frameIntervals.map((f) => f.affected_joint || f.joint))).filter(Boolean) as string[];

      const diagnosticData: DiagnosticCardProps = {
        analysisId: data.analysis_id,
        sessionId: data.session_id,
        status: data.status,
        summary: data.diagnostic_summary || '',
        brokenJoints,
        frameIntervals,
        durationSeconds: data.duration_seconds || 0,
        frameCount: data.frame_count || 0,
        fps: data.fps || 30,
      };

      setActiveBrokenIntervals(frameIntervals);
      setActiveTotalFrames(data.frame_count || 0);
      setActiveFps(data.fps || 30);
      setSelectedFinding(null);

      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toISOString(),
        text: data.assistant_message || `Kinematic inspection complete for ${file.name}. Diagnostic report generated:`,
        diagnosticData,
        sessionId: data.session_id,
      };

      setMessages((prev) => [
        ...prev.map((m) => (m.id === userMsgId && !m.sessionId ? { ...m, sessionId: data.session_id } : m)),
        assistantMsg,
      ]);
      fetchSessions();
    } catch (err: any) {
      console.error(err);
      const errDetail = err?.response?.data?.detail || err.message || 'Upload processing failed';
      const errorMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toISOString(),
        text: `Kinematic inspection error: ${errDetail}`,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsUploading(false);
    }
  };

  const handleSendMessage = async (prompt: string, audio?: Blob | null) => {
    let audioBase64: string | undefined;
    if (audio) {
      try {
        audioBase64 = await blobToBase64(audio);
      } catch (e) {
        console.error('Failed to convert voice memo blob', e);
      }
    }

    const userText = prompt
      ? (audio ? `${prompt} [Voice memo attached]` : prompt)
      : (audio ? '[Voice memo instructions recorded]' : '');

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: 'user',
      timestamp: new Date().toISOString(),
      text: userText,
      sessionId: activeSessionId || undefined,
    };

    setMessages((prev) => [...prev, userMsg]);

    if (!activeSessionId) {
      const reply: ChatMessage = {
        id: `assistant-${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toISOString(),
        text: 'Please upload or drop a BVH motion file to run kinematic analysis and interactive repairs.',
      };
      setMessages((prev) => [...prev, reply]);
      return;
    }

    setIsGenerating(true);
    try {
      const res = await axios.post(`${API_BASE_URL}/sessions/${activeSessionId}/chat`, {
        message: prompt || (audio ? 'Analyze voice memo repair instructions' : ''),
        asset_id: activeBvhId || undefined,
        audio_base64: audioBase64,
        audio_mime: audio?.type || (audioBase64 ? 'audio/webm' : undefined),
      });
      const data = res.data;

      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toISOString(),
        text: data.reply,
        sessionId: activeSessionId,
        proposedPlan: data.proposed_plan || undefined,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      console.error(err);
      const errDetail = err?.response?.data?.detail || err.message || 'Chat service failed';
      const errorMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toISOString(),
        text: `Error processing kinematic request: ${errDetail}`,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSelectFinding = (findingId: string, frameStart: number, joint?: string) => {
    setSelectedFinding({
      findingId,
      frameStart,
      joint,
      timestamp: Date.now(),
    });
    setMobileViewMode('viewport');
  };

  const handleApproveRepair = async (
    messageId: string,
    planId: string,
    approvalId: string,
    customPrompt?: string,
    selectedJoints?: string[]
  ) => {
    setActivePlanId(planId);
    setActiveApprovalId(approvalId);
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === messageId
          ? {
              ...msg,
              isApproved: true,
              approvalId,
              diagnosticData: msg.diagnosticData
                ? { ...msg.diagnosticData, isApproved: true, approvalId }
                : undefined,
            }
          : msg
      )
    );
    const feedbackMsg: ChatMessage = {
      id: `system-approved-${Date.now()}`,
      sender: 'assistant',
      timestamp: new Date().toISOString(),
      text: `Repair plan authorized (Approval ID: ${approvalId}). Multi-agent execution pipeline unblocked.${
        customPrompt ? ` Custom instructions recorded: "${customPrompt}"` : ''
      }${selectedJoints && selectedJoints.length > 0 ? ` Targeted joints: ${selectedJoints.join(', ')}` : ''}`,
    };
    setMessages((prev) => [...prev, feedbackMsg]);
    fetchSessions();

    const targetSessionId = activeSessionId;
    if (!targetSessionId) return;

    const rosterMsgId = `roster-${Date.now()}`;
    const initialRosterMsg: ChatMessage = {
      id: rosterMsgId,
      sender: 'assistant',
      timestamp: new Date().toISOString(),
      text: 'Synthesizing dynamic multi-agent roster tailored to detected broken frames...',
      agentRoster: [],
      sessionId: targetSessionId,
    };
    setMessages((prev) => [...prev, initialRosterMsg]);

    const streamUrl = `${API_BASE_URL}/sessions/${targetSessionId}/agent-stream`;
    const eventSource = new EventSource(streamUrl);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.event === 'AGENT_SPAWNED' && data.agent) {
          setMessages((prev) =>
            prev.map((msg) => {
              if (msg.id !== rosterMsgId) return msg;
              const currentRoster = msg.agentRoster || [];
              const exists = currentRoster.some((a) => a.agent_id === data.agent.agent_id);
              const nextRoster = exists
                ? currentRoster.map((a) => (a.agent_id === data.agent.agent_id ? data.agent : a))
                : [...currentRoster, data.agent];
              return { ...msg, agentRoster: nextRoster };
            })
          );
        } else if (data.event === 'AGENT_STATUS' && data.agent_id) {
          setMessages((prev) =>
            prev.map((msg) => {
              if (msg.id !== rosterMsgId) return msg;
              const currentRoster = msg.agentRoster || [];
              const nextRoster = currentRoster.map((a) =>
                a.agent_id === data.agent_id ? { ...a, status: data.status } : a
              );
              return { ...msg, agentRoster: nextRoster };
            })
          );
        } else if (data.event === 'ROSTER_COMPLETE') {
          if (Array.isArray(data.agents)) {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === rosterMsgId
                  ? {
                      ...msg,
                      agentRoster: data.agents,
                      text: 'Dynamic multi-agent roster synthesized and active:',
                    }
                  : msg
              )
            );
          }
        } else if (data.event === 'REPAIR_COMPLETED') {
          setMessages((prev) =>
            prev.map((msg) => {
              if (msg.id === rosterMsgId && msg.agentRoster && msg.agentRoster.length > 0) {
                return {
                  ...msg,
                  agentRoster: msg.agentRoster.map((a) => ({
                    ...a,
                    status: 'COMPLETED',
                  })),
                };
              }
              return msg;
            })
          );
          eventSource.close();
        }
      } catch {
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
    };

    try {
      const formData = new FormData();
      formData.append('session_id', targetSessionId);
      formData.append('plan_id', planId);
      formData.append('approval_id', approvalId);
      if (activeBvhId) formData.append('bvh_id', activeBvhId);
      if (customPrompt) formData.append('prompt', customPrompt);
      if (selectedJoints && selectedJoints.length > 0) {
        formData.append('selected_joints', JSON.stringify(selectedJoints));
      }

      const genRes = await axios.post(`${API_BASE_URL}/generate_code`, formData);
      const initialRoster: DynamicAgent[] = Array.isArray(genRes.data?.roster)
        ? genRes.data.roster.map((a: DynamicAgent) => ({ ...a, status: 'SPAWNED' }))
        : [];

      if (initialRoster.length > 0) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === rosterMsgId
              ? {
                  ...msg,
                  agentRoster: initialRoster,
                  text: 'Dynamic multi-agent roster synthesized and active:',
                }
              : msg
          )
        );
      }

      await new Promise((r) => setTimeout(r, 600));

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === rosterMsgId
            ? {
                ...msg,
                agentRoster: (msg.agentRoster || []).map((a) => ({
                  ...a,
                  status: 'THINKING',
                })),
              }
            : msg
        )
      );

      await new Promise((r) => setTimeout(r, 700));

      const runRes = await axios.post(`${API_BASE_URL}/runs`, {
        session_id: targetSessionId,
        plan_id: planId,
        approval_id: approvalId,
        prompt: customPrompt,
        selected_joints: selectedJoints,
      });
      const runData = runRes.data;
      if (runData.asset_id) {
        setActiveBvhId(runData.asset_id);
        setRepairedBvhId(runData.asset_id);
        setActiveFilename((prev) => (prev ? `repaired_${prev.replace(/^repaired_/, '')}` : 'repaired_motion.bvh'));
        setActiveBrokenIntervals([]);
        setSelectedFinding(null);
      }
      if (runData.script_code) {
        setCurrentScriptCode(runData.script_code);
      }
      const outcomeStatus = runData.outcome_status || (runData.status === 'COMPLETED' ? 'COMPLETED' : 'PARTIALLY_REPAIRED');
      const summaryMsg = runData.summary_message || runData.metrics?.summary_message || (outcomeStatus === 'COMPLETED' ? 'Motion repair completed successfully.' : 'Partial motion repair completed.');
      const repairCardMsg: ChatMessage = {
        id: `repair-complete-${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toISOString(),
        text: summaryMsg,
        repairData: {
          assetId: runData.asset_id,
          filename: activeFilename ? `repaired_${activeFilename.replace(/^repaired_/, '')}` : undefined,
          repairedFileUrl: runData.repaired_bvh_url || runData.repaired_file_url || `${API_BASE_URL}/bvh/${runData.asset_id}`,
          scriptCode: runData.script_code || '',
          metrics: {
            execution_time_seconds: runData.metrics?.execution_duration_seconds ?? runData.metrics?.execution_time_seconds ?? 0,
            agents_executed: runData.metrics?.agents_executed ?? (initialRoster.length || 2),
            qa_passed: runData.qa_status === 'passed' || runData.metrics?.qa_passed === true,
            outcome_status: outcomeStatus,
            summary_message: summaryMsg,
            fixed_findings: runData.fixed_findings || runData.metrics?.fixed_findings || [],
            unresolved_findings: runData.unresolved_findings || runData.metrics?.unresolved_findings || [],
          },
        },
        sessionId: targetSessionId,
      };

      await new Promise((r) => setTimeout(r, 400));

      setMessages((prev) => [
        ...prev.map((msg) => {
          if (msg.id === rosterMsgId && msg.agentRoster) {
            return {
              ...msg,
              agentRoster:
                msg.agentRoster.length > 0
                  ? msg.agentRoster.map((a) => ({
                      ...a,
                      status: 'COMPLETED',
                    }))
                  : [
                      {
                        agent_id: 'repaired-1',
                        role: 'Kinematic Solver',
                        status: 'COMPLETED',
                      },
                    ],
            };
          }
          return msg;
        }),
        repairCardMsg,
      ]);
      eventSource.close();
      fetchSessions();
    } catch (err: any) {
      console.error(err);
      eventSource.close();
      const errDetail = err?.response?.data?.detail || err.message || 'Repair execution failed';
      const errorMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toISOString(),
        text: `Repair could not be completed: ${errDetail}`,
      };
      setMessages((prev) => [
        ...prev.map((msg) => {
          if (msg.agentRoster) {
            return {
              ...msg,
              agentRoster:
                msg.agentRoster.length > 0
                  ? msg.agentRoster.map((a) => ({
                      ...a,
                      status: a.status === 'COMPLETED' ? 'COMPLETED' : 'FAILED',
                    }))
                  : [
                      {
                        agent_id: 'err-1',
                        role: 'Kinematic Solver',
                        status: 'FAILED',
                      },
                    ],
            };
          }
          return msg;
        }),
        errorMsg,
      ]);
    }
  };

  const handleAuthorizeProposedPlan = async (
    messageId: string,
    plan: ProposedPlanData
  ) => {
    const targetSessionId = plan.session_id || activeSessionId;
    if (!targetSessionId) return;

    try {
      const sessRes = await axios.get(`${API_BASE_URL}/workflow-sessions/${targetSessionId}`);
      const analysisId = sessRes.data.analysis_id;

      const analysisRes = await axios.get(`${API_BASE_URL}/analyses/${analysisId}`);
      const allFindings = analysisRes.data.findings || [];
      let selectedFids: string[] = [];
      if (plan.selected_joints && plan.selected_joints.length > 0) {
        const jSet = new Set(plan.selected_joints);
        selectedFids = allFindings
          .filter((f: any) => jSet.has(f.affected_joint))
          .map((f: any) => f.finding_id);
      }
      if (selectedFids.length === 0) {
        selectedFids = allFindings.map((f: any) => f.finding_id);
      }

      const planRes = await axios.post(`${API_BASE_URL}/analyses/${analysisId}/repair-plan`, {
        session_id: targetSessionId,
        selected_finding_ids: selectedFids,
        selected_joints: plan.selected_joints,
        user_prompt: plan.user_prompt,
      });

      const planId = planRes.data.plan_id;
      const planVersion = planRes.data.version;

      const approveRes = await axios.post(`${API_BASE_URL}/repair-plans/${planId}/approve`, {
        session_id: targetSessionId,
        plan_id: planId,
        repair_plan_version: planVersion,
        selected_finding_ids: selectedFids,
        selected_joints: plan.selected_joints,
        user_prompt: plan.user_prompt,
        confirmed: true,
      });

      const approvalId = approveRes.data.approval_id;
      await handleApproveRepair(
        messageId,
        planId,
        approvalId,
        plan.user_prompt,
        plan.selected_joints
      );
    } catch (err: any) {
      console.error(err);
      const detail = err?.response?.data?.detail || err.message || 'Authorization failed';
      alert(`Could not authorize proposed plan: ${detail}`);
    }
  };

  const handleInspectCode = (scriptCode: string) => {
    setCurrentScriptCode(scriptCode);
    setIsCodeDrawerOpen(true);
  };

  const handleExecuteEditedScript = async (editedCode: string) => {
    if (!activeSessionId) return;
    setIsExecutingScript(true);
    try {
      const res = await axios.post(`${API_BASE_URL}/run_blender`, {
        session_id: activeSessionId,
        plan_id: activePlanId || undefined,
        approval_id: activeApprovalId || undefined,
        bvh_id: activeBvhId || undefined,
        script_code: editedCode,
      });
      const data = res.data;
      if (data.asset_id) {
        setActiveBvhId(data.asset_id);
        setRepairedBvhId(data.asset_id);
        setActiveFilename((prev) => (prev ? `repaired_${prev.replace(/^repaired_/, '')}` : 'repaired_motion.bvh'));
        setActiveBrokenIntervals([]);
        setSelectedFinding(null);
      }
      setCurrentScriptCode(editedCode);
      const updateMsg: ChatMessage = {
        id: `re-repair-${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toISOString(),
        text: 'White-Box Blender script re-executed successfully with modified code:',
        repairData: {
          assetId: data.asset_id,
          filename: activeFilename ? `repaired_${activeFilename.replace(/^repaired_/, '')}` : undefined,
          repairedFileUrl: data.repaired_file_url || data.repaired_bvh_url || `${API_BASE_URL}/bvh/${data.asset_id}`,
          scriptCode: editedCode,
          metrics: {
            execution_time_seconds: data.metrics?.execution_duration_seconds ?? data.metrics?.execution_time_seconds ?? 0,
            agents_executed: 1,
            qa_passed: data.qa_status === 'passed' || data.metrics?.qa_passed === true,
          },
        },
        sessionId: activeSessionId,
      };
      const lastRosterId = [...messages].reverse().find((m) => m.agentRoster && m.agentRoster.length > 0)?.id;
      setMessages((prev) => [
        ...prev.map((msg) => {
          if (lastRosterId && msg.id === lastRosterId && msg.agentRoster && msg.agentRoster.length > 0) {
            return {
              ...msg,
              agentRoster: msg.agentRoster.map((a) => ({
                ...a,
                status: 'COMPLETED',
              })),
            };
          }
          return msg;
        }),
        updateMsg,
      ]);
      setIsCodeDrawerOpen(false);
      fetchSessions();
    } catch (err: any) {
      console.error(err);
      const errDetail = err?.response?.data?.detail || err.message || 'Script execution failed';
      alert(`Blender script execution failed: ${errDetail}`);
    } finally {
      setIsExecutingScript(false);
    }
  };

  const handleDeclineRepair = (messageId: string) => {
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === messageId
          ? {
              ...msg,
              isDeclined: true,
              diagnosticData: msg.diagnosticData
                ? { ...msg.diagnosticData, isDeclined: true }
                : undefined,
            }
          : msg
      )
    );
    const feedbackMsg: ChatMessage = {
      id: `system-declined-${Date.now()}`,
      sender: 'assistant',
      timestamp: new Date().toISOString(),
      text: 'Kinematic repair was declined. The analysis remains archived without multi-agent execution.',
    };
    setMessages((prev) => [...prev, feedbackMsg]);
    fetchSessions();
  };

  const handleWindowDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOverWindow(true);
  };

  const handleWindowDragLeave = (e: DragEvent) => {
    e.preventDefault();
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setIsDragOverWindow(false);
  };

  const handleWindowDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOverWindow(false);
    if (sessionUploadCount >= 5) {
      const limitMsg: ChatMessage = {
        id: `limit-${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toISOString(),
        text: 'Upload limit reached: A maximum of 5 files can be uploaded in a single chat session. Start a new thread (Cmd+N) to analyze more files.',
      };
      setMessages((prev) => [...prev, limitMsg]);
      return;
    }
    const file = e.dataTransfer.files?.[0];
    if (file && file.name.toLowerCase().endsWith('.bvh')) {
      setStagedFile(file);
    }
  };

  const hasActiveWorkspace = Boolean(activeSessionId || activeBvhId || isUploading || messages.length > 0);

  return (
    <div
      onDragOver={handleWindowDragOver}
      onDragLeave={handleWindowDragLeave}
      onDrop={handleWindowDrop}
      className="flex flex-col h-screen w-screen bg-zinc-950 text-zinc-100 overflow-hidden font-sans antialiased"
    >
      <header className="h-11 border-b border-white/[0.08] bg-[#090c13] backdrop-blur-2xl flex items-center justify-between px-3 sm:px-4 shrink-0 select-none z-30">
        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid="mobile-sidebar-toggle"
            onClick={handleToggleSidebar}
            className="md:hidden p-1.5 text-zinc-400 hover:text-white hover:bg-white/[0.06] rounded-lg transition-colors cursor-pointer"
            title="Toggle threads drawer"
          >
            <PanelLeft className="w-4 h-4" />
          </button>

          <div className="flex items-center gap-2 sm:gap-2.5">
            <div className="w-6 h-6 rounded-lg bg-blue-600 flex items-center justify-center text-white shadow-[0_0_12px_rgba(37,99,235,0.4)]">
              <MotionPatchLogo size="sm" className="text-white" />
            </div>
            <span className="font-semibold text-sm tracking-tight text-white font-display hidden xs:inline sm:inline">MotionPatch</span>
          </div>
        </div>

        {hasActiveWorkspace && (
          <div className="flex md:hidden items-center p-0.5 bg-zinc-900/90 border border-white/[0.08] rounded-lg text-[11px] font-medium">
            <button
              type="button"
              data-testid="mobile-tab-viewport"
              onClick={() => setMobileViewMode('viewport')}
              className={`px-2 py-0.5 rounded-md transition-colors flex items-center gap-1 cursor-pointer ${
                mobileViewMode === 'viewport'
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <Box className="w-3 h-3" />
              <span>3D</span>
            </button>
            <button
              type="button"
              data-testid="mobile-tab-chat"
              onClick={() => setMobileViewMode('chat')}
              className={`px-2 py-0.5 rounded-md transition-colors flex items-center gap-1 cursor-pointer ${
                mobileViewMode === 'chat'
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <Bot className="w-3 h-3" />
              <span>Inspector</span>
            </button>
            <button
              type="button"
              data-testid="mobile-tab-split"
              onClick={() => setMobileViewMode('split')}
              className={`px-2 py-0.5 rounded-md transition-colors flex items-center gap-1 cursor-pointer ${
                mobileViewMode === 'split'
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <Columns2 className="w-3 h-3" />
              <span>Split</span>
            </button>
          </div>
        )}

        {activeFilename && hasActiveWorkspace ? (
          <div className="hidden md:flex items-center gap-2 bg-[#0c1017] border border-white/[0.07] px-3 py-1 rounded-full text-xs">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />
            <span className="text-zinc-200 font-mono text-[11px] truncate font-medium max-w-xs">
              {activeFilename}
            </span>
          </div>
        ) : null}

        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid="keyboard-shortcuts-btn"
            onClick={() => setIsShortcutsOpen(true)}
            className="px-2 sm:px-2.5 py-1 rounded-lg text-xs font-medium text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.06] border border-transparent hover:border-white/[0.08] transition-colors flex items-center gap-1.5 cursor-pointer"
            title="Keyboard Shortcuts (?)"
          >
            <Keyboard className="w-3.5 h-3.5 text-blue-400" />
            <span className="text-[11px] hidden sm:inline">Shortcuts</span>
            <kbd className="px-1 py-0.2 rounded bg-zinc-800 border border-white/[0.1] text-[9px] font-mono text-zinc-400 hidden sm:inline">?</kbd>
          </button>
        </div>
      </header>

      <div className="flex-1 flex flex-col md:flex-row overflow-hidden relative">
        {isDragOverWindow && (
          <div className="absolute inset-0 z-50 bg-blue-950/80 border-2 border-dashed border-blue-400/80 backdrop-blur-sm flex flex-col items-center justify-center gap-2 pointer-events-none">
            <p className="text-base font-semibold text-blue-200">Drop BVH file to stage for analysis</p>
            <p className="text-xs text-blue-400">Release mouse to stage file in the composer</p>
          </div>
        )}

        <SessionSidebar
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onNewSession={handleNewSession}
          isOpen={isSidebarOpen}
          onToggleOpen={handleToggleSidebar}
          isLoading={isLoadingSessions}
          sessionError={sessionFetchError}
          onRetry={fetchSessions}
        />

        {!hasActiveWorkspace ? (
          <main className="flex-1 flex flex-col items-center justify-center p-6 overflow-y-auto relative bg-[#080a10]">
            <div className="flex flex-col items-center justify-center text-center max-w-2xl w-full mx-auto gap-6 my-auto py-6">
              <div className="w-14 h-14 rounded-2xl bg-blue-950/70 border border-blue-800/60 flex items-center justify-center text-blue-400 shadow-[0_0_24px_rgba(37,99,235,0.35)] select-none">
                <MotionPatchLogo size={28} className="text-blue-400" />
              </div>

              <div className="flex flex-col gap-2 max-w-md">
                <h1 className="text-2xl font-bold font-display text-white tracking-tight">
                  What motion would you like to inspect?
                </h1>
                <p className="text-xs text-zinc-400 leading-relaxed">
                  Attach a <span className="text-blue-400 font-mono">.bvh</span> file to inspect kinematic trajectories, detect anomalies, and execute multi-agent repairs.
                </p>
              </div>

              <div className="w-full">
                <MultimodalPromptBar
                  onSendMessage={handleSendMessage}
                  onFileUpload={handleFileUpload}
                  disabled={isUploading || isGenerating}
                  isGenerating={isGenerating}
                  externalStagedFile={stagedFile}
                  onClearExternalStagedFile={() => setStagedFile(null)}
                  uploadCount={sessionUploadCount}
                  maxUploads={5}
                />
              </div>
            </div>
          </main>
        ) : (
          <>
            <main
              data-testid="main-viewport-container"
              className={`w-full md:w-[60%] md:h-full overflow-hidden bg-zinc-950 relative md:border-r border-white/[0.08] ${
                mobileViewMode === 'viewport'
                  ? 'flex-1 h-full flex flex-col'
                  : mobileViewMode === 'split'
                  ? 'h-[42vh] shrink-0 flex flex-col border-b'
                  : 'hidden md:flex md:flex-col'
              }`}
            >
              <Viewport3D
                bvhId={activeBvhId}
                originalBvhId={originalBvhId}
                repairedBvhId={repairedBvhId}
                filename={activeFilename}
                brokenIntervals={activeBrokenIntervals}
                totalFrames={activeTotalFrames}
                fps={activeFps}
                selectedFinding={selectedFinding}
                mode={comparisonMode}
                onModeChange={setComparisonMode}
                showIdleOverlay={false}
              />
            </main>

            <section
              data-testid="main-inspector-container"
              className={`w-full md:w-[40%] md:h-full shrink-0 flex-col bg-[#0a0d14] overflow-hidden shadow-2xl z-10 ${
                mobileViewMode === 'chat'
                  ? 'flex-1 h-full flex'
                  : mobileViewMode === 'split'
                  ? 'flex-1 min-h-[280px] flex'
                  : 'hidden md:flex'
              }`}
            >
              <ChatStream
                messages={messages}
                activeSessionId={activeSessionId}
                onSelectFinding={handleSelectFinding}
                onDropFile={handleFileUpload}
                isUploading={isUploading}
                isGenerating={isGenerating}
                onApproveRepair={handleApproveRepair}
                onDeclineRepair={handleDeclineRepair}
                onInspectCode={handleInspectCode}
                onAuthorizeProposedPlan={handleAuthorizeProposedPlan}
              />
              <MultimodalPromptBar
                onSendMessage={handleSendMessage}
                onFileUpload={handleFileUpload}
                disabled={isUploading || isGenerating}
                isGenerating={isGenerating}
                externalStagedFile={stagedFile}
                onClearExternalStagedFile={() => setStagedFile(null)}
                diagnosticStatus={activeBrokenIntervals.length === 0 && activeSessionId ? 'CLEAN' : undefined}
                hasAnomalies={activeBrokenIntervals.length > 0}
                uploadCount={sessionUploadCount}
                maxUploads={5}
              />
            </section>
          </>
        )}
      </div>

      <WhiteBoxCodeDrawer
        isOpen={isCodeDrawerOpen}
        onClose={() => setIsCodeDrawerOpen(false)}
        initialScript={currentScriptCode}
        onExecuteScript={handleExecuteEditedScript}
        isExecuting={isExecutingScript}
      />

      <KeyboardShortcutsModal
        isOpen={isShortcutsOpen}
        onClose={() => setIsShortcutsOpen(false)}
      />
    </div>
  );
}
