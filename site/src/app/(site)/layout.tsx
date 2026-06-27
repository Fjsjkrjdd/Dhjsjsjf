import Header from "@/components/site/Header";
import Footer from "@/components/site/Footer";
import { getSettings } from "@/lib/content";

export default async function SiteLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const settings = await getSettings();
  return (
    <>
      <Header logoText={settings.logoText} phone={settings.phone} />
      <main className="flex-1">{children}</main>
      <Footer settings={settings} />
    </>
  );
}
