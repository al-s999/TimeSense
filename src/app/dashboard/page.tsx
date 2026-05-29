import GreetingCard from "@/components/cards/GreetingCard";
import ActivityPreview from "@/components/cards/ActivityPreview";
import NotificationPreview from "@/components/cards/NotificationPreview";
import RevealOnScroll from "@/components/RevealOnScroll";
import DoorStatusCard from "@/components/DoorStatusCard";

export default function DashboardPage() {
  return (
    <div>
      <h1 className="text-4xl font-extrabold">Dashboard</h1>

      <div className="mt-6">
        <RevealOnScroll>
          <GreetingCard />
        </RevealOnScroll>
      </div>

      <div className="mt-8">
        <RevealOnScroll delayMs={40}>
          <DoorStatusCard />
        </RevealOnScroll>
      </div>

      <div className="mt-8 grid grid-cols-2 gap-8 items-stretch">
        <RevealOnScroll delayMs={80} className="h-full">
          <ActivityPreview />
        </RevealOnScroll>
        <RevealOnScroll delayMs={160} className="h-full">
          <NotificationPreview />
        </RevealOnScroll>
      </div>
    </div>
  );
}
