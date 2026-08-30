import React, { useEffect, useRef, useMemo } from 'react';
import { Canvas, useFrame, useLoader } from '@react-three/fiber';
import { OrbitControls, Grid, Html } from '@react-three/drei';
import * as THREE from 'three';
import { BVHLoader } from 'three/examples/jsm/loaders/BVHLoader.js';

function BvhModel({ url }: { url: string }) {
  const bvh = useLoader(BVHLoader as any, url);
  const mixer = useRef<THREE.AnimationMixer>(null);

  // We need to keep the helper alive during unmount/remount
  const helper = useMemo(() => {
    if (!bvh) return null;
    return new THREE.SkeletonHelper(bvh.skeleton.bones[0]);
  }, [bvh]);

  useEffect(() => {
    if (bvh && helper) {
      const m = new THREE.AnimationMixer(bvh.skeleton.bones[0]);
      mixer.current = m;
      
      const action = m.clipAction(bvh.clip);
      action.play();
    }
    return () => {
      if (mixer.current) mixer.current.stopAllAction();
    };
  }, [bvh, helper]);

  useFrame((_, delta) => {
    if (mixer.current) {
      mixer.current.update(delta);
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
      <div className="text-white text-lg font-medium animate-pulse whitespace-nowrap">
        Loading 3D Model...
      </div>
    </Html>
  );
}

export default function Viewer({ bvhId }: { bvhId: string }) {
  const url = `http://localhost:8000/bvh/${bvhId}`;

  return (
    <Canvas camera={{ position: [0, 100, 400], fov: 50 }}>
      <color attach="background" args={['#111']} />
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 10]} intensity={1} />
      
      <OrbitControls />
      <Grid infiniteGrid fadeDistance={1000} sectionColor="#444" cellColor="#222" />
      
      <React.Suspense fallback={<Loader />}>
        <BvhModel url={url} />
      </React.Suspense>
    </Canvas>
  );
}
