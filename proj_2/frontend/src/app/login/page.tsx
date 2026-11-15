import { AuthForm } from "@/components/AuthForm";
import { PageShell } from "@/components/PageShell";

export default function LoginPage() {
  return (
    <PageShell title="Log in" showFreshness={false}>
      <AuthForm mode="login" />
    </PageShell>
  );
}
