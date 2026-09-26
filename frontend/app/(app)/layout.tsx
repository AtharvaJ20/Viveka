import Nav from "@/components/layout/Nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Nav showSignIn={false} />
      <main
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          paddingInline: "var(--s6)",
          paddingTop: "var(--s8)",
          paddingBottom: "var(--s12)",
        }}
      >
        {children}
      </main>
    </>
  );
}
