import "./globals.css";
import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";
import PageTransition from "@/components/PageTransition";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen bg-[#FCEEEE] text-neutral-900">
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 px-10 py-8">
              <Topbar />
              <div className="mt-8">
                <PageTransition>{children}</PageTransition>
              </div>
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
