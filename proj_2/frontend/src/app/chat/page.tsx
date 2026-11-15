import { PageShell } from "@/components/PageShell";
import { ChatPanel } from "./ChatPanel";

// This is the /chat page. ChatPanel checks who's signed in and shows their rooms.
export default function ChatPage() {
  return (
    <PageShell
      title="Group Chat"
      lede="Invite other PackPlate users and make dining plans together."
      showFreshness={false}
    >
      <ChatPanel />
    </PageShell>
  );
}
