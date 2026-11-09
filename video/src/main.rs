//! `FILM=film.toml film <fframes command>`, e.g. `render -o out.mp4`, `frame s03_card@1s -o f.png`.
//! Reads build/plan.json, which `uv run prep.py <film.toml>` writes; refuses a stale plan.
use fframes::{CombinedMediaProvider, EncoderOptions, MediaDirectory, MediaProvider, RenderOptions, cli};
use fframes_skia_renderer::{SkiaFFramesRenderer, SkiaPipelineConcurrencyPolicy, SkiaPipelineConfig, metal::SkiaMetalCtx};
use film::{Film, FilmMedia, HEIGHT, Plan, WIDTH};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

fn mtime(p: &Path) -> Option<std::time::SystemTime> {
    std::fs::metadata(p).and_then(|m| m.modified()).ok()
}

fn main() -> ExitCode {
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let film_path = PathBuf::from(std::env::var("FILM").unwrap_or_else(|_| "film.toml".into()));
    let film_path = std::fs::canonicalize(&film_path).unwrap_or(film_path);
    let plan_path = here.join("build/plan.json");
    let plan: Plan = match std::fs::read_to_string(&plan_path).map_err(|e| e.to_string()).and_then(|s| serde_json::from_str(&s).map_err(|e| e.to_string())) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("cannot read {}: {e}\nrun: uv run prep.py {}", plan_path.display(), film_path.display());
            return ExitCode::FAILURE;
        }
    };
    if PathBuf::from(&plan.source) != film_path {
        eprintln!("build/plan.json was made from {}, not {}\nrun: uv run prep.py {}", plan.source, film_path.display(), film_path.display());
        return ExitCode::FAILURE;
    }
    if let (Some(f), Some(p)) = (mtime(&film_path), mtime(&plan_path)) {
        if f > p {
            eprintln!("{} changed after the last prep\nrun: uv run prep.py {}", film_path.display(), film_path.display());
            return ExitCode::FAILURE;
        }
    }
    let master_gain_db = plan.master_gain_db;
    let media = FilmMedia::new().expect("media");
    let dir = MediaDirectory::read_folder(here.join("build/media")).expect("build/media");
    let rt = dir.process_media_source().expect("build media");
    let all = CombinedMediaProvider::from([&media as &dyn MediaProvider, &rt]);
    let video = Film::new(plan);
    let gpu = SkiaMetalCtx::new(WIDTH, HEIGHT).expect("GPU context");

    // The libav that fframes links has no h264_videotoolbox, so encode with libx264. Frames are
    // drawn on the GPU (Skia Metal) and converted to YUV there. CRF=<n> overrides quality.
    let crf: &'static str = Box::leak(std::env::var("CRF").unwrap_or_else(|_| "18".into()).into_boxed_str());
    let params: &'static [(&'static str, &'static str)] = Box::leak(vec![("crf", crf), ("preset", "fast")].into_boxed_slice());
    let video_encoder_options = EncoderOptions { preferred_encoder: Some("libx264"), codec_params: Some(params), ..Default::default() };
    cli::new(
        &video,
        RenderOptions {
            media: Some(&all),
            default_font: "Inter",
            audio_mix: fframes::AudioMixOptions { master_gain_db, ..Default::default() },
            video_encoder_options,
            ..Default::default()
        },
    )
    .backend(
        SkiaFFramesRenderer::new_metal(
            &gpu,
            SkiaPipelineConfig { concurrency_policy: SkiaPipelineConcurrencyPolicy::MaxPerformance, ..Default::default() },
        )
        .expect("skia renderer"),
    )
    .preview(fframes_native_player::cli_preview)
    .default_output("out.mp4")
    .run()
}
