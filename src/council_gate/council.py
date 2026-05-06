import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from council_gate.providers import Provider
from council_gate.types import Review

log = logging.getLogger(__name__)


class Council:
    def __init__(
        self,
        seats: list[Provider],
        generator_provider: str | None = None,
    ) -> None:
        self.generator_provider = generator_provider
        self.seats = [s for s in seats if s.provider != generator_provider]
        if not self.seats:
            raise ValueError(
                f"no seats remain after excluding generator_provider={generator_provider!r}"
            )

    def run(self, artifact: str, system_prompt: str, progress: bool = True) -> list[Review]:
        if progress:
            print(
                f"council-gate: dispatching to {len(self.seats)} seats: "
                f"{', '.join(s.model_id for s in self.seats)}",
                file=sys.stderr,
            )
        results: list[Review] = []
        with ThreadPoolExecutor(max_workers=len(self.seats)) as ex:
            future_to_seat = {
                ex.submit(self._run_one, s, artifact, system_prompt): s
                for s in self.seats
            }
            # Iterate as they complete so progress feedback is real-time.
            for fut in as_completed(future_to_seat):
                review = fut.result()
                results.append(review)
                if progress:
                    mark = "✓" if review.ok else "✗"
                    print(f"  {mark} {review.model_id}", file=sys.stderr)
        return results

    @staticmethod
    def _run_one(seat: Provider, artifact: str, prompt: str) -> Review:
        # Adapter trust boundary: surface the error on Review.error rather than
        # crashing the whole council. Logged + visible, not swallowed.
        try:
            return seat.review(artifact, prompt)
        except Exception as e:
            log.warning("adapter %s raised: %s", seat.model_id, e)
            return Review(
                model_id=seat.model_id,
                provider=seat.provider,
                findings=[],
                error=f"{type(e).__name__}: {e}",
            )
