import Link from "next/link";

export default function Home() {
  return (
    <main>
      <h1>PackPlate</h1>
      <p>Find somewhere on campus where everyone in your group can eat.</p>
      <ul>
        <li>
          <Link href="/locations">Dining locations</Link>
        </li>
        <li>
          <Link href="/group">Group filter</Link>
        </li>
      </ul>
    </main>
  );
}
