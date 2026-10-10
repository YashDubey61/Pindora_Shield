import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";

/**
 * Simple hardcoded molecule:
 * 2 atoms + 1 bond
 */
function MoleculeModel() {
  return (
    <group>
      {/* Atom A (Red) */}
      <mesh position={[-1.2, 0, 0]}>
        <sphereGeometry args={[0.4, 32, 32]} />
        <meshStandardMaterial color="#ff4d4d" />
      </mesh>

      {/* Atom B (Green) */}
      <mesh position={[1.2, 0, 0]}>
        <sphereGeometry args={[0.4, 32, 32]} />
        <meshStandardMaterial color="#4dff4d" />
      </mesh>

      {/* Bond */}
      <mesh rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.1, 0.1, 2.4, 32]} />
        <meshStandardMaterial color="#cccccc" />
      </mesh>
    </group>
  );
}

export default function MoleculeViewer() {
  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: "#0f172a",
      }}
    >
      <Canvas
        camera={{ position: [0, 0, 6], fov: 50 }}
        style={{ width: "100%", height: "100%" }}
        onCreated={({ gl }) => {
          // Debug: confirm WebGL renderer
          console.log("WebGL Renderer:", gl instanceof THREE.WebGLRenderer);
        }}
      >
        {/* Background (DEBUG friendly) */}
        <color attach="background" args={["#ffffff"]} />

        {/* Lights */}
        <ambientLight intensity={0.6} />
        <directionalLight position={[5, 5, 5]} intensity={1} />
        <directionalLight position={[-5, -5, -5]} intensity={0.5} />

        {/* Molecule */}
        <MoleculeModel />

        {/* Controls */}
        <OrbitControls enableDamping />
      </Canvas>
    </div>
  );
}
