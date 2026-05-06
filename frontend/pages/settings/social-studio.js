import { useEffect } from 'react';
import { useRouter } from 'next/router';

export default function SocialStudioSettingsRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/settings?tab=social');
  }, [router]);

  return (
    <div className="p-6 max-w-4xl">
      <p className="text-gray-500 text-sm">Redirecting to Settings → Social Studio...</p>
    </div>
  );
}
