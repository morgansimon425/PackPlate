import { AccountPanel } from "@/components/AccountPanel";
import { PageShell } from "@/components/PageShell";

export default function AccountPage() {
  return (
    <PageShell title="My account" showFreshness={false}>
      <AccountPanel />
    </PageShell>
  );
}
