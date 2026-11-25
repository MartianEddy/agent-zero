"use client";

/**
 * Hero scene: a refractive glass "claim" core with evidence sources orbiting it.
 * Lime nodes support, coral nodes challenge, sky nodes add context. Everything is procedural, so no model or texture downloads.
 *
 * Performance: capped pixel ratio, low transmission resolution and samples, instanced
 * nodes, a performance monitor that lowers quality on slow devices, and a render loop
 * that stops when the hero is off screen (see EvidenceSceneLoader).
 */

import { Environment, Float, Lightformer, MeshTransmissionMaterial, PerformanceMonitor, Sparkles } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Bloom, EffectComposer, Vignette } from "@react-three/postprocessing";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";

const COLORS = { supports: "#a3ff47", challenges: "#ff6b5a", context: "#4cc3ff", teal: "#14d3b4" } as const;

type Source = { radius: number; speed: number; phase: number; tilt: number; color: string; size: number };

function seeded(seed: number) {
  let value = seed;
  return () => {
    value = (value * 16807) % 2147483647;
    return (value - 1) / 2147483646;
  };
}

function GlassCore({ quality }: { quality: "high" | "low" }) {
  const outer = useRef<THREE.Mesh>(null);
  const inner = useRef<THREE.Mesh>(null);
  useFrame((state, delta) => {
    if (outer.current) {
      outer.current.rotation.y += delta * 0.22;
      outer.current.rotation.z += delta * 0.05;
    }
    if (inner.current) {
      inner.current.rotation.y -= delta * 0.5;
      const pulse = 1 + Math.sin(state.clock.elapsedTime * 1.6) * 0.04;
      inner.current.scale.setScalar(pulse);
    }
  });
  return (
    <Float speed={1.4} rotationIntensity={0.25} floatIntensity={0.6}>
      <mesh ref={outer}>
        <torusKnotGeometry args={[0.82, 0.3, 220, 36, 2, 3]} />
        <MeshTransmissionMaterial
          samples={quality === "high" ? 6 : 3}
          resolution={quality === "high" ? 512 : 256}
          transmission={1}
          thickness={1.2}
          roughness={0.08}
          ior={1.45}
          chromaticAberration={0.35}
          anisotropy={0.3}
          distortion={0.15}
          distortionScale={0.3}
          temporalDistortion={0.06}
          backside
          backsideThickness={0.5}
          color="#e9ffd8"
          attenuationColor="#a3ff47"
          attenuationDistance={2.4}
        />
      </mesh>
      {/* The verified "core" seen through the glass */}
      <mesh ref={inner}>
        <sphereGeometry args={[0.34, 48, 48]} />
        <meshStandardMaterial color={COLORS.supports} emissive={COLORS.supports} emissiveIntensity={1.6} toneMapped={false} />
      </mesh>
    </Float>
  );
}

function OrbitRing({ radius, tilt, color, speed }: { radius: number; tilt: [number, number]; color: string; speed: number }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((_, delta) => { if (ref.current) ref.current.rotation.z += delta * speed; });
  return (
    <mesh ref={ref} rotation={[tilt[0], tilt[1], 0]}>
      <torusGeometry args={[radius, 0.008, 12, 220]} />
      <meshBasicMaterial color={color} transparent opacity={0.55} toneMapped={false} />
    </mesh>
  );
}

function SourceNode({ source }: { source: Source }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    const mesh = ref.current;
    if (!mesh) return;
    const angle = source.phase + state.clock.elapsedTime * source.speed;
    const flat = Math.sin(angle) * source.radius;
    mesh.position.set(Math.cos(angle) * source.radius, flat * Math.sin(source.tilt), flat * Math.cos(source.tilt));
  });
  return (
    <mesh ref={ref}>
      <sphereGeometry args={[source.size, 20, 20]} />
      <meshStandardMaterial color={source.color} emissive={source.color} emissiveIntensity={3} toneMapped={false} />
    </mesh>
  );
}

function Rig({ children }: { children: React.ReactNode }) {
  const group = useRef<THREE.Group>(null);
  useFrame((state, delta) => {
    const g = group.current;
    if (!g) return;
    g.rotation.y += delta * 0.06;
    g.rotation.x = THREE.MathUtils.damp(g.rotation.x, -state.pointer.y * 0.22, 3, delta);
    g.rotation.z = THREE.MathUtils.damp(g.rotation.z, state.pointer.x * 0.12, 3, delta);
  });
  return <group ref={group}>{children}</group>;
}

function Scene({ quality }: { quality: "high" | "low" }) {
  const sources = useMemo<Source[]>(() => {
    const random = seeded(7);
    return Array.from({ length: 11 }, (_, index) => ({
      radius: 2.05 + random() * 1.1,
      speed: (0.18 + random() * 0.22) * (index % 2 ? 1 : -1),
      phase: random() * Math.PI * 2,
      tilt: (random() - 0.5) * 1.6,
      color: index % 5 === 0 ? COLORS.challenges : index % 3 === 0 ? COLORS.context : COLORS.supports,
      size: 0.05 + random() * 0.04,
    }));
  }, []);

  return (
    <>
      <color attach="background" args={["#070c09"]} />
      <ambientLight intensity={0.4} />
      <Rig>
        <GlassCore quality={quality} />
        <OrbitRing radius={1.9} tilt={[Math.PI / 2.4, 0.2]} color={COLORS.supports} speed={0.15} />
        <OrbitRing radius={2.55} tilt={[Math.PI / 1.8, -0.4]} color={COLORS.teal} speed={-0.1} />
        <OrbitRing radius={3.15} tilt={[Math.PI / 2.1, 0.6]} color={COLORS.context} speed={0.07} />
        {sources.map((source, index) => <SourceNode key={index} source={source} />)}
        <Sparkles count={quality === "high" ? 70 : 30} scale={[8, 6, 6]} size={2.2} speed={0.3} opacity={0.6} color={COLORS.supports} />
      </Rig>
      {/* Procedural studio lighting: soft panels the glass reflects and refracts. */}
      <Environment resolution={256} frames={1}>
        <Lightformer form="rect" intensity={4} color="#ffffff" position={[0, 4, -6]} scale={[10, 2, 1]} />
        <Lightformer form="rect" intensity={3} color={COLORS.supports} position={[-6, 1, 2]} rotation-y={Math.PI / 2} scale={[8, 2, 1]} />
        <Lightformer form="rect" intensity={3} color={COLORS.teal} position={[6, -1, 2]} rotation-y={-Math.PI / 2} scale={[8, 2, 1]} />
        <Lightformer form="ring" intensity={2.5} color={COLORS.context} position={[0, -4, 3]} scale={3} />
      </Environment>
      {quality === "high" && (
        <EffectComposer multisampling={0}>
          <Bloom mipmapBlur luminanceThreshold={0.9} intensity={0.9} radius={0.7} />
          <Vignette offset={0.3} darkness={0.7} />
        </EffectComposer>
      )}
    </>
  );
}

export default function EvidenceScene({ paused }: { paused: boolean }) {
  const [quality, setQuality] = useState<"high" | "low">("high");
  return (
    <Canvas
      dpr={quality === "high" ? [1, 1.5] : 1}
      frameloop={paused ? "never" : "always"}
      camera={{ position: [0, 0, 8], fov: 38 }}
      gl={{ antialias: false, powerPreference: "high-performance", alpha: false }}
      aria-hidden
    >
      <PerformanceMonitor onDecline={() => setQuality("low")} flipflops={2} />
      <Scene quality={quality} />
    </Canvas>
  );
}
