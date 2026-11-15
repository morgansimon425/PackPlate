import { AuthForm } from "@/components/AuthForm";
import { PageShell } from "@/components/PageShell";

export default function SignupPage() {
  return (
    <PageShell
      title="Create an account"
      lede="You don’t need an account to check menus. It’s for features that need to know who you are, like chatting with friends."
      showFreshness={false}
    >
      <AuthForm mode="signup" />
    </PageShell>
  );
}
