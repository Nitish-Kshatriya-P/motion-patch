import { useEffect, useRef, useMemo, useState, Suspense, useCallback } from 'react';
import { Canvas, useFrame, useLoader } from '@react-three/fiber';
import { OrbitControls, Grid, Html } from '@react-three/drei';
import * as THREE from 'three';
import { BVHLoader } from 'three/examples/jsm/loaders/BVHLoader.js';
import { Play, Pause, RotateCcw, Eye } from 'lucide-react';
import TimelineScrubber from './TimelineScrubber';
import ComparisonControls, { type ComparisonMode, syncMixerTime } from './ComparisonControls';
import type { FindingItem } from './DiagnosticCard';

export type { ComparisonMode };

interface BvhModelProps {
  url: string;
  isPlaying: boolean;
  isLooping: boolean;
  playbackRate: number;
  fps: number;
  currentFrame: number;
  seekRequest: { frame: number; timestamp: number } | null;
  brokenIntervals?: FindingItem[];
  selectedJoint?: string | null;
  onFrameUpdate?: (frame: number) => void;
  onTotalFramesDetected?: (frames: number) => void;
  onPlaybackEnded?: () => void;
  isGhost?: boolean;
  opacity?: number;
  skeletonColor?: number;
  isMaster?: boolean;
}

function BvhModel({
  url,
  isPlaying,
  isLooping,
  playbackRate,
  fps,
  currentFrame,
  seekRequest,
  brokenIntervals = [],
  selectedJoint,
  onFrameUpdate,
  onTotalFramesDetected,
  onPlaybackEnded,
  isGhost = false,
  opacity = 0.45,
  skeletonColor,
  isMaster = true,
}: BvhModelProps) {
  const bvh = useLoader(BVHLoader as any, url);
  const mixer = useRef<THREE.AnimationMixer | null>(null);
  const actionRef = useRef<THREE.AnimationAction | null>(null);
  const lastFrameRef = useRef<number>(-1);

  const sphereGeometry = useMemo(() => new THREE.SphereGeometry(1.8, 16, 16), []);
  const redSphereMaterial = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: 0xef4444,
        emissive: 0xef4444,
        emissiveIntensity: 0.9,
        roughness: 0.2,
        transparent: isGhost,
        opacity: isGhost ? opacity : 1.0,
      }),
    [isGhost, opacity]
  );
  const amberSphereMaterial = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: 0xf59e0b,
        emissive: 0xf59e0b,
        emissiveIntensity: 0.9,
        roughness: 0.2,
        transparent: isGhost,
        opacity: isGhost ? opacity : 1.0,
      }),
    [isGhost, opacity]
  );

  const baseLineColor = useMemo(
    () => new THREE.Color(skeletonColor ?? (isGhost ? 0xf59e0b : 0x38bdf8)),
    [skeletonColor, isGhost]
  );
  const redLineColor = useMemo(() => new THREE.Color(0xef4444), []);
  const amberLineColor = useMemo(() => new THREE.Color(0xf59e0b), []);

  const helper = useMemo(() => {
    if (!bvh) return null;
    const h = new THREE.SkeletonHelper(bvh.skeleton.bones[0]);
    if (isGhost) {
      const mat = h.material as THREE.LineBasicMaterial;
      mat.transparent = true;
      mat.opacity = opacity;
      mat.depthWrite = false;
    }
    return h;
  }, [bvh, isGhost, opacity]);

  useEffect(() => {
    if (bvh && bvh.clip && isMaster) {
      const clipFrames = Math.max(1, Math.round(bvh.clip.duration * fps));
      onTotalFramesDetected?.(clipFrames);
    }
  }, [bvh, fps, isMaster, onTotalFramesDetected]);

  useEffect(() => {
    if (bvh && helper) {
      const animationMixer = new THREE.AnimationMixer(bvh.skeleton.bones[0]);
      mixer.current = animationMixer;
      const action = animationMixer.clipAction(bvh.clip);
      actionRef.current = action;
      action.setLoop(isLooping ? THREE.LoopRepeat : THREE.LoopOnce, Infinity);
      action.clampWhenFinished = !isLooping;
      action.timeScale = playbackRate;
      action.play();
      action.paused = !isPlaying;
    }
    return () => {
      if (mixer.current) mixer.current.stopAllAction();
    };
  }, [bvh, helper]);

  useEffect(() => {
    if (actionRef.current) {
      actionRef.current.paused = !isPlaying;
    }
  }, [isPlaying]);

  useEffect(() => {
    if (actionRef.current) {
      actionRef.current.setLoop(isLooping ? THREE.LoopRepeat : THREE.LoopOnce, Infinity);
      actionRef.current.clampWhenFinished = !isLooping;
    }
  }, [isLooping]);

  useEffect(() => {
    if (actionRef.current) {
      actionRef.current.timeScale = playbackRate;
    }
  }, [playbackRate]);

  useEffect(() => {
    if (seekRequest && mixer.current && actionRef.current && bvh) {
      syncMixerTime(mixer.current, actionRef.current, seekRequest.frame, fps, bvh.clip.duration);
      if (bvh.skeleton && bvh.skeleton.bones[0]) {
        bvh.skeleton.bones[0].updateMatrixWorld(true);
      }
      if (helper) {
        helper.updateMatrixWorld(true);
      }
      lastFrameRef.current = seekRequest.frame;
    }
  }, [seekRequest, fps, bvh, helper]);

  useEffect(() => {
    if (!bvh) return;
    const addedSpheres: THREE.Mesh[] = [];
    bvh.skeleton.bones.forEach((bone: THREE.Bone) => {
      const sphere = new THREE.Mesh(sphereGeometry, redSphereMaterial);
      sphere.name = '__highlightSphere__';
      sphere.visible = false;
      bone.add(sphere);
      addedSpheres.push(sphere);
    });
    return () => {
      addedSpheres.forEach((s) => {
        if (s.parent) s.parent.remove(s);
      });
    };
  }, [bvh, sphereGeometry, redSphereMaterial]);

  useEffect(() => {
    if (!bvh || !helper) return;

    const activeSeverities = new Map<string, string>();
    for (const interval of brokenIntervals) {
      if (currentFrame >= interval.frame_start && currentFrame <= interval.frame_end) {
        const normJoint = interval.joint.toLowerCase().replace(/[^a-z0-9]/g, '');
        const existing = activeSeverities.get(normJoint);
        if (!existing || interval.severity.toUpperCase() === 'CRITICAL' || interval.severity.toUpperCase() === 'HIGH') {
          activeSeverities.set(normJoint, interval.severity.toUpperCase());
        }
      }
    }
    if (selectedJoint) {
      const normSel = selectedJoint.toLowerCase().replace(/[^a-z0-9]/g, '');
      if (!activeSeverities.has(normSel)) {
        const matchingInterval = brokenIntervals.find(
          (interval) => interval.joint.toLowerCase().replace(/[^a-z0-9]/g, '') === normSel
        );
        const sev = matchingInterval ? matchingInterval.severity.toUpperCase() : 'HIGH';
        activeSeverities.set(normSel, sev);
      }
    }

    const getHighlightSeverity = (boneName: string): string | null => {
      const normBone = boneName.toLowerCase().replace(/[^a-z0-9]/g, '');
      for (const [normJoint, severity] of activeSeverities.entries()) {
        if (normBone === normJoint || normBone.includes(normJoint) || normJoint.includes(normBone)) {
          return severity;
        }
      }
      return null;
    };

    const colorAttr = helper.geometry.getAttribute('color') as THREE.BufferAttribute;
    if (colorAttr) {
      let j = 0;
      for (let i = 0; i < helper.bones.length; i++) {
        const bone = helper.bones[i];
        if (bone.parent && (bone.parent as any).isBone) {
          const boneSev = getHighlightSeverity(bone.name);
          const parentSev = getHighlightSeverity((bone.parent as THREE.Bone).name);
          const effectiveSev = boneSev || parentSev;
          if (effectiveSev === 'CRITICAL' || effectiveSev === 'HIGH') {
            colorAttr.setXYZ(j, redLineColor.r, redLineColor.g, redLineColor.b);
            colorAttr.setXYZ(j + 1, redLineColor.r, redLineColor.g, redLineColor.b);
          } else if (effectiveSev === 'MEDIUM') {
            colorAttr.setXYZ(j, amberLineColor.r, amberLineColor.g, amberLineColor.b);
            colorAttr.setXYZ(j + 1, amberLineColor.r, amberLineColor.g, amberLineColor.b);
          } else {
            colorAttr.setXYZ(j, baseLineColor.r, baseLineColor.g, baseLineColor.b);
            colorAttr.setXYZ(j + 1, baseLineColor.r, baseLineColor.g, baseLineColor.b);
          }
          j += 2;
        }
      }
      colorAttr.needsUpdate = true;
    }

    bvh.skeleton.bones.forEach((bone: THREE.Bone) => {
      const sphere = bone.children.find((c: THREE.Object3D) => c.name === '__highlightSphere__') as THREE.Mesh | undefined;
      if (sphere) {
        const sev = getHighlightSeverity(bone.name);
        if (sev) {
          sphere.visible = true;
          sphere.material = sev === 'CRITICAL' || sev === 'HIGH' ? redSphereMaterial : amberSphereMaterial;
        } else {
          sphere.visible = false;
        }
      }
    });
  }, [
    currentFrame,
    bvh,
    helper,
    brokenIntervals,
    selectedJoint,
    redLineColor,
    amberLineColor,
    baseLineColor,
    redSphereMaterial,
    amberSphereMaterial,
  ]);

  useFrame((_, delta) => {
    if (!mixer.current || !actionRef.current || !bvh) return;
    if (!isPlaying) {
      if (helper) {
        helper.updateMatrixWorld(true);
      }
      return;
    }
    const clip = bvh.clip;
    const action = actionRef.current;
    mixer.current.update(delta);
    if (bvh.skeleton && bvh.skeleton.bones[0]) {
      bvh.skeleton.bones[0].updateMatrixWorld(true);
    }
    if (helper) {
      helper.updateMatrixWorld(true);
    }

    if (!isMaster) return;

    if (!isLooping && action.time >= clip.duration) {
      action.time = clip.duration;
      syncMixerTime(mixer.current, action, Math.round(clip.duration * fps), fps, clip.duration);
      if (bvh.skeleton && bvh.skeleton.bones[0]) {
        bvh.skeleton.bones[0].updateMatrixWorld(true);
      }
      if (helper) {
        helper.updateMatrixWorld(true);
      }
      onPlaybackEnded?.();
      const endFrame = Math.max(0, Math.round(clip.duration * fps));
      if (endFrame !== lastFrameRef.current) {
        lastFrameRef.current = endFrame;
        onFrameUpdate?.(endFrame);
      }
      return;
    }

    const effectiveTime = isLooping ? action.time % clip.duration : Math.min(action.time, clip.duration);
    const maxFrame = Math.max(0, Math.round(clip.duration * fps));
    const frame = Math.max(0, Math.min(Math.round(effectiveTime * fps), maxFrame));
    if (frame !== lastFrameRef.current) {
      lastFrameRef.current = frame;
      onFrameUpdate?.(frame);
    }
  });

  if (!bvh) return null;

  return (
    <group>
      <primitive object={bvh.skeleton.bones[0]} />
      {helper && <primitive object={helper} />}
    </group>
  );
}

function Loader() {
  return (
    <Html center>
      <div className="flex items-center gap-2.5 bg-zinc-950/90 text-zinc-200 px-4 py-2 rounded-xl border border-white/[0.08] shadow-2xl backdrop-blur-xl text-xs font-mono">
        <div className="w-3.5 h-3.5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <span>Parsing & Loading BVH...</span>
      </div>
    </Html>
  );
}

export interface Viewport3DProps {
  bvhId?: string | null;
  originalBvhId?: string | null;
  repairedBvhId?: string | null;
  filename?: string | null;
  repairedFilename?: string | null;
  brokenIntervals?: FindingItem[];
  totalFrames?: number;
  fps?: number;
  selectedFinding?: {
    findingId?: string;
    frameStart: number;
    joint?: string;
    timestamp?: number;
  } | null;
  onFrameChange?: (frame: number) => void;
  initialMode?: ComparisonMode;
  mode?: ComparisonMode;
  onModeChange?: (mode: ComparisonMode) => void;
  showIdleOverlay?: boolean;
}

export default function Viewport3D({
  bvhId,
  originalBvhId,
  repairedBvhId,
  filename,
  repairedFilename,
  brokenIntervals = [],
  totalFrames,
  fps = 30,
  selectedFinding,
  onFrameChange,
  initialMode,
  mode,
  onModeChange,
  showIdleOverlay = false,
}: Viewport3DProps) {
  const effectiveOriginalBvhId = originalBvhId || bvhId || null;
  const effectiveRepairedBvhId = repairedBvhId || null;

  const [comparisonMode, setComparisonMode] = useState<ComparisonMode>(() => {
    if (mode) return mode;
    if (initialMode) return initialMode;
    return effectiveRepairedBvhId ? 'ghost' : 'original';
  });

  const [isPlaying, setIsPlaying] = useState(true);
  const [isLooping, setIsLooping] = useState(true);
  const [playbackRate, setPlaybackRate] = useState(1.0);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [detectedFrames, setDetectedFrames] = useState(0);
  const [seekRequest, setSeekRequest] = useState<{ frame: number; timestamp: number } | null>(null);
  const [selectedJoint, setSelectedJoint] = useState<string | null>(null);
  const [resetKey, setResetKey] = useState(0);
  const controlsRef = useRef<any>(null);
  const seekCounterRef = useRef(0);

  useEffect(() => {
    if (mode) {
      setComparisonMode(mode);
    }
  }, [mode]);

  useEffect(() => {
    if (effectiveRepairedBvhId) {
      setComparisonMode((prev) => (prev === 'original' ? 'ghost' : prev));
    } else {
      setComparisonMode('original');
    }
  }, [effectiveRepairedBvhId]);

  const effectiveTotalFrames = totalFrames && totalFrames > 0 ? totalFrames : detectedFrames > 0 ? detectedFrames : 100;
  const effectiveFps = fps && fps > 0 ? fps : 30;

  const originalUrl = useMemo(() => {
    if (!effectiveOriginalBvhId) return null;
    return `http://localhost:8000/bvh/${effectiveOriginalBvhId}`;
  }, [effectiveOriginalBvhId]);

  const repairedUrl = useMemo(() => {
    if (!effectiveRepairedBvhId) return null;
    return `http://localhost:8000/bvh/${effectiveRepairedBvhId}`;
  }, [effectiveRepairedBvhId]);

  const handleResetCamera = useCallback(() => {
    if (controlsRef.current) {
      controlsRef.current.reset();
    }
    setResetKey((k) => k + 1);
  }, []);

  const handleSeek = useCallback(
    (frame: number) => {
      const clamped = Math.max(0, Math.min(frame, effectiveTotalFrames - 1));
      seekCounterRef.current += 1;
      setCurrentFrame(clamped);
      setSeekRequest({ frame: clamped, timestamp: performance.now() + seekCounterRef.current });
      onFrameChange?.(clamped);
    },
    [effectiveTotalFrames, onFrameChange]
  );

  const handleStep = useCallback(
    (step: number) => {
      const next = Math.max(0, Math.min(currentFrame + step, effectiveTotalFrames - 1));
      handleSeek(next);
      setIsPlaying(false);
    },
    [currentFrame, effectiveTotalFrames, handleSeek]
  );

  const handleFrameUpdate = useCallback(
    (frame: number) => {
      setCurrentFrame(frame);
      onFrameChange?.(frame);
    },
    [onFrameChange]
  );

  const handleTotalFramesDetected = useCallback((frames: number) => {
    setDetectedFrames(frames);
  }, []);

  const handlePlaybackEnded = useCallback(() => {
    setIsPlaying(false);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = (document.activeElement?.tagName || '').toLowerCase();
      if (activeTag === 'input' || activeTag === 'textarea' || (document.activeElement as HTMLElement)?.isContentEditable) {
        return;
      }

      if (e.code === 'Space') {
        e.preventDefault();
        setIsPlaying((prev) => !prev);
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        const step = e.shiftKey ? -10 : -1;
        handleStep(step);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        const step = e.shiftKey ? 10 : 1;
        handleStep(step);
      } else if (e.key === 'Home') {
        e.preventDefault();
        handleSeek(0);
        setIsPlaying(false);
      } else if (e.key === 'End') {
        e.preventDefault();
        handleSeek(effectiveTotalFrames - 1);
        setIsPlaying(false);
      } else if (e.key === 'l' || e.key === 'L') {
        e.preventDefault();
        setIsLooping((prev) => !prev);
      } else if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        handleResetCamera();
      } else if (e.key === '[') {
        e.preventDefault();
        setPlaybackRate((prev) => (prev <= 0.5 ? 0.25 : prev <= 1.0 ? 0.5 : 1.0));
      } else if (e.key === ']') {
        e.preventDefault();
        setPlaybackRate((prev) => (prev >= 2.0 ? 4.0 : prev >= 1.0 ? 2.0 : 1.0));
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [effectiveTotalFrames, handleResetCamera, handleSeek, handleStep]);

  const handleModeChange = useCallback(
    (mode: ComparisonMode) => {
      setComparisonMode(mode);
      onModeChange?.(mode);
    },
    [onModeChange]
  );

  useEffect(() => {
    if (selectedFinding) {
      setCurrentFrame(selectedFinding.frameStart);
      setSeekRequest({
        frame: selectedFinding.frameStart,
        timestamp: selectedFinding.timestamp || Date.now(),
      });
      setIsPlaying(false);
      setSelectedJoint(selectedFinding.joint || null);
    }
  }, [selectedFinding]);

  const activeDisplayFilename = useMemo(() => {
    if (comparisonMode === 'repaired') {
      return repairedFilename || (filename ? `repaired_${filename.replace(/^repaired_/, '')}` : 'repaired_motion.bvh');
    }
    if (comparisonMode === 'ghost') {
      return filename ? `${filename} vs repaired` : 'Comparison View';
    }
    return filename || null;
  }, [comparisonMode, filename, repairedFilename]);

  return (
    <div className="flex-1 min-w-[450px] relative h-full bg-zinc-950 flex flex-col overflow-hidden select-none">
      <div className="relative flex-1 w-full h-full min-h-0">

        {activeDisplayFilename && (
          <div className="absolute top-4 left-4 z-10 flex items-center gap-2 bg-zinc-900/80 backdrop-blur-xl px-3 py-1.5 rounded-xl border border-white/[0.08] text-xs font-mono text-zinc-300 shadow-xl pointer-events-none">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
            <span className="truncate max-w-[200px]">{activeDisplayFilename}</span>
          </div>
        )}

        {effectiveRepairedBvhId && (
          <ComparisonControls
            mode={comparisonMode}
            onModeChange={handleModeChange}
            originalBvhId={effectiveOriginalBvhId}
            repairedBvhId={effectiveRepairedBvhId}
            fps={effectiveFps}
            currentFrame={currentFrame}
          />
        )}

        <div className="absolute top-4 right-4 z-10 flex items-center gap-1.5 bg-zinc-900/80 backdrop-blur-xl p-1 rounded-xl border border-white/[0.08] shadow-xl">
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            disabled={!effectiveOriginalBvhId && !effectiveRepairedBvhId}
            className="p-1.5 text-zinc-300 hover:text-white hover:bg-white/[0.06] rounded-lg transition-colors disabled:opacity-40 cursor-pointer"
            title={isPlaying ? 'Pause animation' : 'Play animation'}
          >
            {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
          </button>
          <button
            onClick={handleResetCamera}
            className="p-1.5 text-zinc-300 hover:text-white hover:bg-white/[0.06] rounded-lg transition-colors cursor-pointer"
            title="Reset camera view"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="absolute inset-0 pointer-events-none canvas-vignette z-5" />

        <Canvas
          key={resetKey}
          camera={{ position: [0, 100, 400], fov: 50 }}
          className="w-full h-full"
        >
          <color attach="background" args={['#080a10']} />
          <ambientLight intensity={0.6} />
          <directionalLight position={[100, 150, 100]} intensity={1.2} />
          <directionalLight position={[-100, -100, -100]} intensity={0.4} />

          <OrbitControls ref={controlsRef} makeDefault />
          <Grid
            infiniteGrid
            fadeDistance={1200}
            sectionColor="#1e293b"
            cellColor="#0f172a"
            sectionSize={50}
            cellSize={10}
          />

          {effectiveRepairedBvhId ? (
            <>
              {comparisonMode === 'original' && originalUrl && (
                <Suspense fallback={<Loader />}>
                  <BvhModel
                    url={originalUrl}
                    isPlaying={isPlaying}
                    isLooping={isLooping}
                    playbackRate={playbackRate}
                    fps={effectiveFps}
                    currentFrame={currentFrame}
                    seekRequest={seekRequest}
                    brokenIntervals={brokenIntervals}
                    selectedJoint={selectedJoint}
                    skeletonColor={0x38bdf8}
                    isGhost={false}
                    isMaster={true}
                    onFrameUpdate={handleFrameUpdate}
                    onTotalFramesDetected={handleTotalFramesDetected}
                    onPlaybackEnded={handlePlaybackEnded}
                  />
                </Suspense>
              )}

              {comparisonMode === 'repaired' && repairedUrl && (
                <Suspense fallback={<Loader />}>
                  <BvhModel
                    url={repairedUrl}
                    isPlaying={isPlaying}
                    isLooping={isLooping}
                    playbackRate={playbackRate}
                    fps={effectiveFps}
                    currentFrame={currentFrame}
                    seekRequest={seekRequest}
                    brokenIntervals={[]}
                    selectedJoint={null}
                    skeletonColor={0x10b981}
                    isGhost={false}
                    isMaster={true}
                    onFrameUpdate={handleFrameUpdate}
                    onTotalFramesDetected={handleTotalFramesDetected}
                    onPlaybackEnded={handlePlaybackEnded}
                  />
                </Suspense>
              )}

              {comparisonMode === 'ghost' && (
                <>
                  {originalUrl && (
                    <Suspense fallback={null}>
                      <BvhModel
                        url={originalUrl}
                        isPlaying={isPlaying}
                        isLooping={isLooping}
                        playbackRate={playbackRate}
                        fps={effectiveFps}
                        currentFrame={currentFrame}
                        seekRequest={seekRequest}
                        brokenIntervals={brokenIntervals}
                        selectedJoint={selectedJoint}
                        isGhost={true}
                        opacity={0.45}
                        skeletonColor={0xf59e0b}
                        isMaster={false}
                      />
                    </Suspense>
                  )}
                  {repairedUrl && (
                    <Suspense fallback={<Loader />}>
                      <BvhModel
                        url={repairedUrl}
                        isPlaying={isPlaying}
                        isLooping={isLooping}
                        playbackRate={playbackRate}
                        fps={effectiveFps}
                        currentFrame={currentFrame}
                        seekRequest={seekRequest}
                        brokenIntervals={[]}
                        selectedJoint={null}
                        skeletonColor={0x10b981}
                        isGhost={false}
                        opacity={1.0}
                        isMaster={true}
                        onFrameUpdate={handleFrameUpdate}
                        onTotalFramesDetected={handleTotalFramesDetected}
                        onPlaybackEnded={handlePlaybackEnded}
                      />
                    </Suspense>
                  )}
                </>
              )}
            </>
          ) : originalUrl ? (
            <Suspense fallback={<Loader />}>
              <BvhModel
                url={originalUrl}
                isPlaying={isPlaying}
                isLooping={isLooping}
                playbackRate={playbackRate}
                fps={effectiveFps}
                currentFrame={currentFrame}
                seekRequest={seekRequest}
                brokenIntervals={brokenIntervals}
                selectedJoint={selectedJoint}
                skeletonColor={0x38bdf8}
                isGhost={false}
                isMaster={true}
                onFrameUpdate={handleFrameUpdate}
                onTotalFramesDetected={handleTotalFramesDetected}
                onPlaybackEnded={handlePlaybackEnded}
              />
            </Suspense>
          ) : showIdleOverlay ? (
            <Html center>
              <div
                style={{ width: '380px', maxWidth: '90vw' }}
                className="flex flex-col items-center justify-center p-6 rounded-2xl bg-zinc-900/70 border border-white/[0.08] text-center gap-2.5 backdrop-blur-xl shadow-2xl"
              >
                <Eye className="w-8 h-8 text-zinc-500 mb-1" />
                <p className="text-xs font-semibold text-zinc-200">Kinematics Viewport Idle</p>
                <p className="text-[11px] text-zinc-400 leading-relaxed max-w-[320px]">
                  Drop a BVH motion file or select an earlier session to inspect the skeleton animation in 3D.
                </p>
              </div>
            </Html>
          ) : null}
        </Canvas>
      </div>

      <TimelineScrubber
        currentFrame={currentFrame}
        totalFrames={effectiveTotalFrames}
        fps={effectiveFps}
        isPlaying={isPlaying}
        isLooping={isLooping}
        playbackRate={playbackRate}
        brokenIntervals={comparisonMode === 'repaired' ? [] : brokenIntervals}
        onSeek={handleSeek}
        onTogglePlay={() => setIsPlaying(!isPlaying)}
        onStepForward={() => handleStep(1)}
        onStepBackward={() => handleStep(-1)}
        onToggleLoop={() => setIsLooping(!isLooping)}
        onChangePlaybackRate={setPlaybackRate}
        onSelectInterval={(_id, frameStart) => {
          handleSeek(frameStart);
          setIsPlaying(false);
          const match = brokenIntervals.find((i) => i.finding_id === _id);
          if (match) {
            setSelectedJoint(match.joint);
          }
        }}
      />
    </div>
  );
}
