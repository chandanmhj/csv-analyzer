import { useEffect, useRef } from "react";
import * as THREE from "three";

// Faint drifting stars plus the cyan cursor ring, as on the Repo Reader page
export default function Scene() {
  const box = useRef(), ring = useRef();
  useEffect(() => {
    const el = box.current, w = () => el.clientWidth, h = () => el.clientHeight;
    const r = new THREE.WebGLRenderer({ alpha: true }); r.setSize(w(), h()); el.appendChild(r.domElement);
    const scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera(55, w() / h(), 0.1, 100); cam.position.z = 7;
    const pts = new Float32Array(900).map(() => (Math.random() - 0.5) * 24);
    const stars = new THREE.Points(new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(pts, 3)),
      new THREE.PointsMaterial({ size: 0.03, color: 0xf3ece0 }));
    scene.add(stars);
    let mx = 0, raf;
    const move = (e) => { mx = e.clientX / innerWidth - 0.5; if (ring.current) ring.current.style.transform = `translate(${e.clientX - 20}px,${e.clientY - 20}px)`; };
    const resize = () => { r.setSize(w(), h()); cam.aspect = w() / h(); cam.updateProjectionMatrix(); };
    const loop = () => { stars.rotation.y += 0.0004 + mx * 0.0004; r.render(scene, cam); raf = requestAnimationFrame(loop); };
    addEventListener("mousemove", move); addEventListener("resize", resize);
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) r.render(scene, cam); else loop();
    return () => { cancelAnimationFrame(raf); removeEventListener("mousemove", move); removeEventListener("resize", resize); r.dispose(); el.removeChild(r.domElement); };
  }, []);
  return (<><div className="scene" ref={box} /><div className="ring" ref={ring}><i /></div></>);
}
