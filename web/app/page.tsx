import Link from "next/link";
import Intake from "@/components/Intake";

export default function Home() {
  return (
    <section className="mx-auto max-w-[620px] px-4 pt-14 pb-16 sm:pt-24">
      <h1 className="text-[2.6rem] sm:text-6xl font-semibold leading-[1.05]">
        See which AI tools can save your business time.
      </h1>
      <p className="mt-4 text-xl text-soft">
        We read your website, pick the jobs AI can take off your plate, and compare tools we have checked. Nothing gets set up until you say yes.
      </p>
      <Intake />
      <p className="mt-10 text-lg text-soft">
        Just looking? <Link href="/demo" className="font-semibold">See five example businesses</Link>
      </p>
    </section>
  );
}
