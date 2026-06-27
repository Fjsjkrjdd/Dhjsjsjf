import Image from "next/image";

export default function PortraitFrame({
  src,
  alt,
  className = "",
}: {
  src?: string | null;
  alt: string;
  className?: string;
}) {
  return (
    <div className={`relative overflow-hidden rounded-[2rem] ${className}`}>
      {src ? (
        <Image src={src} alt={alt} fill sizes="(max-width:768px) 90vw, 480px" className="object-cover" priority />
      ) : (
        <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-sage to-sage-dark">
          <span className="font-[family-name:var(--font-display)] text-7xl font-semibold text-white/90">
            Н·Ч
          </span>
        </div>
      )}
    </div>
  );
}
