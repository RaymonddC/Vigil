import { Skeleton } from "@/components/ui/skeleton";

export default function PatientsLoading() {
  return (
    <div className="page">
      <div className="page__hd">
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-4 w-48" />
      </div>
      <div className="roster">
        <div className="roster__hd">
          <div></div>
          <div>Bed</div>
          <div>Patient</div>
          <div>Risk</div>
          <div className="col-alert">Latest alert</div>
          <div className="col-vitals">HR · MAP · SpO₂</div>
          <div className="col-ward">Ward</div>
        </div>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="roster__row" aria-hidden="true">
            <div />
            <div><Skeleton className="h-3 w-10" /></div>
            <div><Skeleton className="h-4 w-40" /></div>
            <div><Skeleton className="h-5 w-20 rounded-full" /></div>
            <div className="col-alert"><Skeleton className="h-3 w-32" /></div>
            <div className="col-vitals"><Skeleton className="h-3 w-24" /></div>
            <div className="col-ward"><Skeleton className="h-3 w-12" /></div>
          </div>
        ))}
      </div>
    </div>
  );
}
