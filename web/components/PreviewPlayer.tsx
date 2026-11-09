import type { OwnerBundle } from "@/lib/types";
import { toolById } from "@/lib/catalog";
import { mediaUrl } from "@/lib/api";

type P = OwnerBundle["previews"][string];

export default function PreviewPlayer({ preview }: { preview: P }) {
  const tool = toolById(preview.tool_id);
  const name = tool?.name ?? preview.tool_id;
  const src = mediaUrl(preview.video_url);
  if (preview.status !== "completed" || !src) {
    return (
      <p className="card p-5">
        {preview.status === "capped"
          ? `We have reached today's limit for preview videos, so there is no preview of ${name} yet.`
          : `We could not make a preview of ${name} this time.`}
      </p>
    );
  }
  return (
    <figure className="card p-4 sm:p-5">
      <video src={`${src}#t=0.5`} muted controls playsInline preload="metadata" className="w-full rounded-2xl bg-black max-h-[70vh]" />
      <figcaption className="mt-3 text-base text-soft">
        AI-generated preview of how {name} would work in your business
      </figcaption>
    </figure>
  );
}
